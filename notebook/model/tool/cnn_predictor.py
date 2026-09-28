# =============================================================================
# SKIN CNN PREDICTOR
# Compatible with:
# AdaptiveCNN — SkinDisease 22 Classes
# AMKC v6 + Adaptive GeM + ResNet-18
# =============================================================================

import os
from typing import Union

import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image
from torchvision import models, transforms


# =============================================================================
# CONFIG
# =============================================================================

IMG_SIZE = 224

IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]


# =============================================================================
# ADAPTIVE MULTI-KERNEL CONVOLUTION
# =============================================================================

class AdaptiveMultiKernelConv(nn.Module):

    def __init__(
        self,
        channels=3,
        lambda_scale=0.2,
        init_gate=1.0
    ):
        super().__init__()

        self.lambda_scale = lambda_scale

        self.conv3 = nn.Conv2d(
            channels,
            channels,
            kernel_size=3,
            padding=1,
            bias=False
        )

        self.conv5 = nn.Conv2d(
            channels,
            channels,
            kernel_size=5,
            padding=2,
            bias=False
        )

        # Same initialization as training
        nn.init.zeros_(self.conv3.weight)
        nn.init.zeros_(self.conv5.weight)

        self.a = nn.Parameter(
            torch.tensor(float(init_gate))
        )

        self.b = nn.Parameter(
            torch.tensor(float(init_gate))
        )

    def forward(self, x):

        y3 = (
            torch.tanh(self.a)
            * self.conv3(x)
        )

        y5 = (
            torch.tanh(self.b)
            * self.conv5(x)
        )

        return x + self.lambda_scale * (y3 + y5)


# =============================================================================
# ADAPTIVE GeM
# =============================================================================

class AdaptiveGeM(nn.Module):

    def __init__(
        self,
        p_init=4.0,
        eps=1e-6
    ):
        super().__init__()

        self.p = nn.Parameter(
            torch.tensor(float(p_init))
        )

        self.eps = eps

    def forward(self, x):

        p = torch.clamp(
            self.p,
            min=0.1,
            max=10.0
        )

        x = x.clamp(
            min=self.eps
        )

        x = F.avg_pool2d(
            x.pow(p),
            kernel_size=(
                x.size(-2),
                x.size(-1)
            )
        )

        return x.pow(1.0 / p)


# =============================================================================
# ADAPTIVE CNN
# =============================================================================

class AdaptiveCNN(nn.Module):

    def __init__(
        self,
        num_classes,
        lambda_scale=0.2,
        p_init=4.0,
        pretrained=True
    ):
        super().__init__()

        # ---------------------------------------------------------------------
        # AMKC
        # ---------------------------------------------------------------------

        self.amkc = AdaptiveMultiKernelConv(
            channels=3,
            lambda_scale=lambda_scale,
            init_gate=1.0
        )

        # ---------------------------------------------------------------------
        # RESNET18
        # ---------------------------------------------------------------------

        weights = (
            models.ResNet18_Weights.IMAGENET1K_V1
            if pretrained
            else None
        )

        backbone = models.resnet18(
            weights=weights
        )

        self.backbone = nn.Sequential(
            backbone.conv1,
            backbone.bn1,
            backbone.relu,
            backbone.maxpool,
            backbone.layer1,
            backbone.layer2,
            backbone.layer3,
            backbone.layer4
        )

        # ---------------------------------------------------------------------
        # ADAPTIVE GeM
        # ---------------------------------------------------------------------

        self.pool = AdaptiveGeM(
            p_init=p_init
        )

        self.feature_dim = 512

        # ---------------------------------------------------------------------
        # CLASSIFIER
        # ---------------------------------------------------------------------

        self.dropout = nn.Dropout(0.3)

        self.classifier = nn.Linear(
            self.feature_dim,
            num_classes
        )

    def forward(self, x):

        x = self.amkc(x)

        x = self.backbone(x)

        x = self.pool(x)

        x = torch.flatten(
            x,
            1
        )

        x = self.dropout(x)

        return self.classifier(x)


# =============================================================================
# CNN PREDICTOR
# =============================================================================

class SkinCNNPredictor:

    def __init__(
        self,
        checkpoint_path: str,
        device: str = None
    ):

        # ---------------------------------------------------------------------
        # DEVICE
        # ---------------------------------------------------------------------

        if device is None:
            self.device = torch.device(
                "cuda"
                if torch.cuda.is_available()
                else "cpu"
            )
        else:
            self.device = torch.device(device)

        # ---------------------------------------------------------------------
        # CHECKPOINT
        # ---------------------------------------------------------------------

        if not os.path.exists(checkpoint_path):
            raise FileNotFoundError(
                f"Checkpoint not found: {checkpoint_path}"
            )

        checkpoint = torch.load(
            checkpoint_path,
            map_location=self.device,
            weights_only=False
        )

        # ---------------------------------------------------------------------
        # READ CONFIG FROM CHECKPOINT
        # ---------------------------------------------------------------------

        self.class_names = checkpoint.get(
            "class_names",
            None
        )

        self.num_classes = checkpoint.get(
            "num_classes",
            None
        )

        config = checkpoint.get(
            "config",
            {}
        )

        # Fallback if checkpoint does not contain metadata
        if self.class_names is None:
            raise ValueError(
                "Checkpoint does not contain 'class_names'."
            )

        if self.num_classes is None:
            self.num_classes = len(
                self.class_names
            )

        # ---------------------------------------------------------------------
        # MODEL CONFIG
        # ---------------------------------------------------------------------

        lambda_scale = config.get(
            "lambda_scale",
            0.2
        )

        p_init = config.get(
            "p_init",
            4.0
        )

        # ---------------------------------------------------------------------
        # BUILD MODEL
        # ---------------------------------------------------------------------

        self.model = AdaptiveCNN(
            num_classes=self.num_classes,
            lambda_scale=lambda_scale,
            p_init=p_init,
            pretrained=False
        )

        # ---------------------------------------------------------------------
        # LOAD WEIGHTS
        # ---------------------------------------------------------------------

        if "model_state_dict" in checkpoint:

            state_dict = checkpoint[
                "model_state_dict"
            ]

        else:

            # Support raw state_dict as fallback
            state_dict = checkpoint

        self.model.load_state_dict(
            state_dict,
            strict=True
        )

        self.model = self.model.to(
            self.device
        )

        self.model.eval()

        # ---------------------------------------------------------------------
        # INFERENCE TRANSFORM
        # Same as validation transform
        # ---------------------------------------------------------------------

        self.transform = transforms.Compose([
            transforms.Resize(
                (IMG_SIZE, IMG_SIZE)
            ),
            transforms.ToTensor(),
            transforms.Normalize(
                IMAGENET_MEAN,
                IMAGENET_STD
            )
        ])

        print("=" * 80)
        print("SkinCNNPredictor loaded")
        print("=" * 80)

        print("Device       :", self.device)
        print("Model        : AdaptiveCNN")
        print("Classes      :", self.num_classes)
        print("Image size   :", IMG_SIZE)
        print("Lambda scale :", lambda_scale)
        print("GeM p_init   :", p_init)
        print("Checkpoint   :", checkpoint_path)


    # =========================================================================
    # LOAD IMAGE
    # =========================================================================

    def _load_image(
        self,
        image: Union[str, Image.Image]
    ):

        if isinstance(image, str):

            if not os.path.exists(image):
                raise FileNotFoundError(
                    f"Image not found: {image}"
                )

            image = Image.open(
                image
            )

        elif not isinstance(
            image,
            Image.Image
        ):
            raise TypeError(
                "image must be a file path "
                "or PIL.Image.Image"
            )

        image = image.convert("RGB")

        return image


    # =========================================================================
    # PREDICT TOP-K
    # =========================================================================

    @torch.no_grad()
    def predict(
        self,
        image: Union[str, Image.Image],
        top_k: int = 5
    ):

        image = self._load_image(
            image
        )

        x = self.transform(
            image
        ).unsqueeze(0)

        x = x.to(
            self.device
        )

        # ---------------------------------------------------------------------
        # FORWARD
        # ---------------------------------------------------------------------

        logits = self.model(
            x
        )

        probabilities = torch.softmax(
            logits,
            dim=1
        )[0]

        top_k = min(
            top_k,
            self.num_classes
        )

        scores, indices = torch.topk(
            probabilities,
            k=top_k
        )

        # ---------------------------------------------------------------------
        # RESULT
        # ---------------------------------------------------------------------

        results = []

        for rank, (
            score,
            index
        ) in enumerate(
            zip(scores, indices),
            start=1
        ):

            class_id = int(
                index.item()
            )

            confidence = float(
                score.item()
            )

            results.append({
                "rank": rank,
                "class_id": class_id,
                "disease": self.class_names[
                    class_id
                ],
                "confidence": confidence,
                "confidence_percent":
                    confidence * 100.0
            })

        return results


    # =========================================================================
    # PREDICT TOP-1
    # =========================================================================

    @torch.no_grad()
    def predict_top1(
        self,
        image: Union[str, Image.Image]
    ):

        results = self.predict(
            image,
            top_k=1
        )

        return results[0]


    # =========================================================================
    # SIMPLE PREDICTION
    # =========================================================================

    @torch.no_grad()
    def classify(
        self,
        image: Union[str, Image.Image]
    ):

        result = self.predict_top1(
            image
        )

        return {
            "class_id": result["class_id"],
            "disease": result["disease"],
            "confidence": result["confidence"]
        }