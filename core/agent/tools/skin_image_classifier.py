"""Tool phân loại bệnh da liễu từ ẢNH — CNN (AdaptiveCNN: AMKC + ResNet-18 backbone +
Adaptive GeM pooling, 22 lớp bệnh) huấn luyện sẵn ở `model/` (repo root, xem
`model/test_cnn.py`, `model/tool/cnn_predictor.py` — file này port lại kiến trúc y hệt
để load đúng `model_state_dict` trong checkpoint, KHÔNG import trực tiếp từ `model/` vì
đó là thư mục thử nghiệm ngoài `core/`, không phải dependency Python cài đặt được).

Ảnh vào tool qua object key MinIO (`app/infra/file_storage.py`), KHÔNG phải path đĩa
cục bộ hay base64 — luồng đầy đủ: FE `POST /uploads` -> `FileAttachmentDto.id` (=
object key) -> `SendMessageInput.attachments` -> Core forward qua `TurnRequest.attachments`
(`app/agent/schemas.py`) -> `worker.py::_human_message_content` chèn `object_key` vào
text của `HumanMessage` -> agent tự đọc thấy rồi copy làm tham số gọi tool này.

QUAN TRỌNG — kết quả tool này KHÔNG phải clinical evidence: đây là xác suất phân loại
ảnh của 1 CNN (không phải bác sĩ, không có tiền sử/triệu chứng khác của bệnh nhân), nên
theo đúng nguyên tắc evidence của `SYSTEM_PROMPT` (`graph.py` mục 2/5) — chỉ được coi là
GIẢ THUYẾT cần đối chiếu tiếp qua `search_disease_guidelines`/`lookup_dermo_term`/
`ground_medical_entities`, KHÔNG được khẳng định thẳng thành chẩn đoán.
"""

import asyncio
import difflib
from io import BytesIO
from typing import Any, cast

import torch
import torch.nn as nn
import torch.nn.functional as F
from langchain.tools import ToolRuntime, tool
from PIL import Image
from torchvision import models, transforms  # pyright: ignore[reportMissingTypeStubs]

from agent.state.context import AgentContext
from app.core.config import settings
from app.infra.file_storage import get_object_bytes

IMG_SIZE = 224
IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]


# =============================================================================
# KIẾN TRÚC MODEL — PHẢI khớp y hệt lúc train (`model/tool/cnn_predictor.py`) để
# `load_state_dict(strict=True)` không lỗi.
# =============================================================================


class AdaptiveMultiKernelConv(nn.Module):
    def __init__(
        self,
        channels: int = 3,
        lambda_scale: float = 0.2,
        init_gate: float = 1.0,
    ):
        super().__init__()
        self.lambda_scale = lambda_scale
        self.conv3 = nn.Conv2d(
            channels, channels, kernel_size=3, padding=1, bias=False
        )
        self.conv5 = nn.Conv2d(
            channels, channels, kernel_size=5, padding=2, bias=False
        )
        nn.init.zeros_(self.conv3.weight)
        nn.init.zeros_(self.conv5.weight)
        self.a = nn.Parameter(torch.tensor(float(init_gate)))
        self.b = nn.Parameter(torch.tensor(float(init_gate)))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        y3 = torch.tanh(self.a) * self.conv3(x)
        y5 = torch.tanh(self.b) * self.conv5(x)
        return x + self.lambda_scale * (y3 + y5)


class AdaptiveGeM(nn.Module):
    def __init__(self, p_init: float = 4.0, eps: float = 1e-6):
        super().__init__()
        self.p = nn.Parameter(torch.tensor(float(p_init)))
        self.eps = eps

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        p = torch.clamp(self.p, min=0.1, max=10.0)
        x = x.clamp(min=self.eps)
        x = F.avg_pool2d(x.pow(p), kernel_size=(x.size(-2), x.size(-1)))
        return x.pow(1.0 / p)


class AdaptiveCNN(nn.Module):
    def __init__(
        self,
        num_classes: int,
        lambda_scale: float = 0.2,
        p_init: float = 4.0,
        pretrained: bool = True,
    ):
        super().__init__()
        self.amkc = AdaptiveMultiKernelConv(
            channels=3, lambda_scale=lambda_scale, init_gate=1.0
        )

        weights = models.ResNet18_Weights.IMAGENET1K_V1 if pretrained else None
        backbone = models.resnet18(weights=weights)
        self.backbone = nn.Sequential(
            backbone.conv1,
            backbone.bn1,
            backbone.relu,
            backbone.maxpool,
            backbone.layer1,
            backbone.layer2,
            backbone.layer3,
            backbone.layer4,
        )

        self.pool = AdaptiveGeM(p_init=p_init)
        self.feature_dim = 512
        self.dropout = nn.Dropout(0.3)
        self.classifier = nn.Linear(self.feature_dim, num_classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.amkc(x)
        x = self.backbone(x)
        x = self.pool(x)
        x = torch.flatten(x, 1)
        x = self.dropout(x)
        return self.classifier(x)


# =============================================================================
# PREDICTOR — singleton lazy (load checkpoint tốn vài giây, chỉ load 1 lần/process)
# =============================================================================


class SkinCNNPredictor:
    def __init__(self, checkpoint_path: str):
        self.device = torch.device("cpu")

        checkpoint = torch.load(
            checkpoint_path, map_location=self.device, weights_only=False
        )

        self.class_names: list[str] = checkpoint["class_names"]
        self.num_classes: int = checkpoint.get(
            "num_classes", len(self.class_names)
        )
        config = checkpoint.get("config", {})

        self.model = AdaptiveCNN(
            num_classes=self.num_classes,
            lambda_scale=config.get("lambda_scale", 0.2),
            p_init=config.get("p_init", 4.0),
            pretrained=False,
        )
        self.model.load_state_dict(checkpoint["model_state_dict"], strict=True)
        self.model.eval()

        self.transform = transforms.Compose(
            [
                transforms.Resize((IMG_SIZE, IMG_SIZE)),
                transforms.ToTensor(),
                transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
            ]
        )

    @torch.no_grad()
    def predict(
        self, image_bytes: bytes, top_k: int = 5
    ) -> list[dict[str, Any]]:
        image = Image.open(BytesIO(image_bytes)).convert("RGB")
        x = cast(torch.Tensor, self.transform(image)).unsqueeze(0).to(self.device)

        logits = self.model(x)
        probabilities = torch.softmax(logits, dim=1)[0]
        top_k = min(top_k, self.num_classes)
        scores, indices = torch.topk(probabilities, k=top_k)

        return [
            {
                "rank": rank,
                "disease": self.class_names[int(index.item())],
                "confidence": float(score.item()),
            }
            for rank, (score, index) in enumerate(zip(scores, indices), start=1)
        ]


_predictor: SkinCNNPredictor | None = None


def get_predictor() -> SkinCNNPredictor:
    global _predictor
    if _predictor is None:
        _predictor = SkinCNNPredictor(settings.SKIN_CNN_CHECKPOINT_PATH)
    return _predictor


def _format_predictions(results: list[dict[str, Any]]) -> str:
    lines = [
        f"{r['rank']}. {r['disease']} — {r['confidence'] * 100:.1f}%"
        for r in results
    ]
    return "\n".join(lines)


def _resolve_object_key(object_key: str, turn_keys: list[str]) -> str:
    """LLM hay chép sai 1-2 ký tự trong `object_key` (uuid hex 32 ký tự) -> sửa lại theo
    danh sách ảnh THẬT của turn hiện tại (chỉ ảnh user vừa đính kèm, không đụng ảnh khác
    trong bucket). Không có danh sách (vd turn resume) thì giữ nguyên giá trị LLM đưa."""
    if not turn_keys or object_key in turn_keys:
        return object_key
    if len(turn_keys) == 1:
        return turn_keys[0]
    close = difflib.get_close_matches(object_key, turn_keys, n=1, cutoff=0.6)
    return close[0] if close else object_key


@tool
async def classify_skin_image(object_key: str, runtime: ToolRuntime[AgentContext, Any]) -> str:
    """Phân loại ảnh tổn thương da bằng CNN đã huấn luyện (22 lớp bệnh da liễu phổ
    biến: Acne, Eczema, Psoriasis, Tinea, SkinCancer...), trả về top-5 kèm % tin cậy.

    CHỈ gọi khi tin nhắn người dùng có phần "[Ảnh đính kèm]" với `object_key` tương ứng
    — copy ĐÚNG giá trị `object_key` đó, không tự bịa.

    KẾT QUẢ TOOL NÀY LÀ GIẢ THUYẾT, KHÔNG PHẢI CHẨN ĐOÁN: đây là xác suất phân loại ảnh
    thuần tuý, không biết tiền sử/triệu chứng khác của người dùng. BẮT BUỘC đối chiếu
    tên bệnh top-1 (và top-2 nếu tin cậy gần nhau) qua `search_disease_guidelines`
    hoặc `lookup_dermo_term` để lấy CLINICAL_EVIDENCE trước khi trả lời — KHÔNG được nói
    thẳng "bạn bị X" chỉ dựa vào % tin cậy của tool này.

    Args:
        object_key: Object key MinIO của ảnh, lấy nguyên văn từ phần "[Ảnh đính kèm]"
            trong tin nhắn người dùng (field `object_key`).
    """
    ctx: AgentContext = runtime.context  # type: ignore[assignment]
    object_key = _resolve_object_key(object_key, ctx.image_keys)
    image_bytes = await get_object_bytes(object_key)
    if image_bytes is None:
        return f"Không tìm thấy ảnh với object_key='{object_key}'."

    predictor = get_predictor()
    # torch inference (CPU) là tác vụ đồng bộ, chặn CPU — chạy trong thread riêng để
    # không block event loop của Agent Worker (đang xử lý các turn/hội thoại khác).
    results = await asyncio.to_thread(predictor.predict, image_bytes, 5)

    return (
        "Kết quả phân loại ảnh (CNN, KHÔNG phải chẩn đoán y khoa):\n"
        + _format_predictions(results)
        + "\n\nCần đối chiếu tên bệnh top-1 qua search_disease_guidelines/lookup_dermo_term "
        "trước khi kết luận."
    )
