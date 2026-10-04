# Kiến trúc multi-agent: Orchestrator + Specialist subagents

## Context

Hiện tại Agent là **1 graph đơn** (`app/agent/graph.py`): `pre_step → reasoning ⇄ tool_wait
→ finalize`, 1 LLM duy nhất (`app/agent/llm.py::get_llm`), registry tool chỉ có `ask_user`
(`app/agent/tools/`). Không có xử lý ảnh (`SendMessageInput.attachments` mới là metadata,
"nội dung file tải riêng"), không có RAG tri thức y khoa (chỉ có long-term memory per-user
trong Qdrant collection `agent_memories`), `ChatSourceDto`/`sources` đã khai trong DTO nhưng
chưa implement.

Yêu cầu: áp dụng kiến trúc **subagent chuyên môn** bên cạnh **1 Orchestrator agent chính**,
theo khung ở mục 3 của brief:

- **3.1 Orchestrator** — *điều phối reasoning*, KHÔNG tự chẩn đoán: understand case → task
  plan → dispatch specialists → collect evidence → detect missing/conflicting → request
  additional execution → aggregate.
- **3.2 Vision Expert** — image → quality assessment → lesion detection → morphology
  (color/shape/border/texture/distribution) → disease classifier → structured visual
  report. **Multi-tool** (YOLO/seg, ResNet/classifier, model da liễu chuyên biệt, image
  quality model); VLM *diễn giải* output của tool thành clinical representation, không tự
  làm toàn bộ vision reasoning (triết lý DermAgent).
- **3.3 Clinical Attribute Agent** — patient-side evidence: raw symptoms → chuẩn hoá thuật
  ngữ y khoa → clinical attributes (temporal/severity/distribution) → differential clues →
  *rồi mới* query RAG → guidelines/evidence. **RAG là evidence provider, không phải agent
  "đoán bệnh"**.

Tài liệu tham chiếu: `docs/agent/` (DermAgent paper, `derm_3r.pdf` — Reason/Reflect/Refine,
"Principles ... AI in dermatology").

## 1. Nguyên tắc thiết kế (chốt trước khi code)

1. **Orchestrator điều phối, không phải source-of-truth y khoa.** Nó lập kế hoạch, phân
   việc, phát hiện thiếu/mâu thuẫn, tổng hợp — mọi "bằng chứng y khoa" đến từ specialist +
   RAG, không phải từ prompt của Orchestrator.
2. **Specialist = subgraph có trace riêng, KHÔNG phải tool đục.** Mỗi bước của specialist
   phát `reasoning.step_*` ra SSE (kèm nhãn agent) — giữ tính *traceable decision-making*.
   Nếu bọc specialist thành 1 tool `run()` duy nhất thì FE chỉ thấy 1 dòng "gọi tool", mất
   toàn bộ giá trị giải trình.
3. **RAG = evidence provider.** Query RAG chạy *sau* khi đã có clinical attributes có cấu
   trúc; kết quả trả về là passage + citation (`ChatSource`), không phải "bệnh X".
4. **Giữ nguyên hợp đồng SSE Turn/Step/Reasoning** (`core/app/kien-truc-agent.md`,
   `docs/async-api-doc.md`). Chỉ **thêm 1 field optional `agent`** trên reasoning event +
   `ReasoningStepDto` để FE nhóm/gán nhãn. Không đổi máy trạng thái turn.
5. **Coexist, không thay thế.** Turn hội thoại thường (vd "kem chống nắng nào tốt?") vẫn
   chạy graph cũ. Chỉ turn được **triage** là "ca da liễu" (có ảnh HOẶC mô tả triệu chứng
   lâm sàng) mới vào `orchestrator_graph`. Giảm rủi ro + không phá regression.
6. **Vision models chạy ở service riêng.** Worker LangGraph không nhúng torch/onnx/YOLO
   (nặng, cần GPU). Vision Expert tools gọi HTTP tới `vision-service` (FastAPI riêng) —
   đúng triết lý "tách tiến trình" đã có (Core ↔ Worker).

## 2. Bức tranh tổng thể

```
                 RabbitMQ agent_request_queue
                          │
                          ▼
              ┌───────────────────────┐
              │  worker.py (_on_msg)  │
              │        triage         │  có ảnh? có triệu chứng lâm sàng?
              └─────────┬──────────┬──┘
              không ─── │          │ ─── có
                        ▼          ▼
       agent_graph (cũ, giữ nguyên)   orchestrator_graph  ◀── checkpointer (thread_id=message_id)
                                            │
   ┌────────────────────────────────────────┼───────────────────────────────────┐
   │ understand_case → plan → dispatch → collect → reconcile → reflect → aggregate│
   │                              │            ▲        │                          │
   │                              │            └────────┘ need_more (round++)      │
   │                              │            │ ask_user (interrupt) ── pause     │
   └──────────────────────────────┼────────────────────────────────────────────────┘
                                  ▼ dispatch gọi specialist subgraphs
        ┌───────────────────────────────┐   ┌───────────────────────────────┐
        │  vision_expert_graph          │   │  clinical_attribute_graph     │
        │  quality → lesion → morphology│   │  normalize → extract → clues  │
        │  → classifier → visual_report │   │  → retrieve_evidence (RAG)    │
        └──────────┬────────────────────┘   └──────────┬────────────────────┘
                   │ HTTP                               │ Qdrant `derma_guidelines`
                   ▼                                    ▼
        vision-service (FastAPI, GPU)          ingestion offline từ docs/agent/*
        /quality /detect /classify

  Mọi node (orchestrator + specialist) → get_stream_writer() → Redis agent:events:* → SSE
  reasoning_trace tích luỹ → agent_response_queue (persist) + memory.distill_and_store
```

## 3. Prerequisite — Phase 0 (làm trước, không phụ thuộc multi-agent)

### 3.1 Ảnh: upload + storage + resolve trong worker

Vision cần **bytes ảnh thật**. Hiện `attachments` chỉ có `{id,name,size,type}`.

- Hạ tầng: thêm **MinIO** (S3-compatible) vào `docker-compose.yml` (pattern như `qdrant`
  trong `plans/long-term-memory.md`), hoặc thư mục local `var/uploads/` cho dev.
- Endpoint mới: `POST /api/v1/conversations/{id}/attachments` (multipart) → lưu blob → trả
  `{ id, url, type, width, height }`. Route → `AttachmentService` → storage client
  (`app/infra/storage_client.py`, cùng phong cách `redis_client.py`).
- `FileAttachmentDto` + `SendMessageInput.attachments[]` thêm `url` (hoặc `storage_key`).
- `TurnRequest` mang theo `image_refs: list[ImageRef]` (`{attachment_id, url, mime}`).
- Worker: `app/agent/vision/image_loader.py::load_images(refs) -> list[LoadedImage]` (tải
  bytes từ storage, verify mime/size, downscale nếu > N px).
- Giới hạn: chỉ nhận `image/jpeg|png|webp`, ≤ 8 MB, ≤ 4 ảnh/turn.

### 3.2 Knowledge base guidelines — Qdrant collection mới

- Collection **`derma_guidelines`** (TÁCH khỏi `agent_memories`) — cùng embedding
  `models/gemini-embedding-001` @ 768d (khớp `EMBEDDING_DIM`).
- `app/infra/qdrant_client.py`: thêm `search_guidelines(vector, limit, filter)` +
  `ensure_guidelines_collection()`. Payload point: `{ source, title, citation_key,
  section, lang, url, text }` — khớp `ChatSourceDto` sẵn có.
- Ingestion offline: `scripts/ingest_guidelines.py` — đọc PDF trong `docs/agent/` + nguồn
  guideline (AAD, DermNet, phác đồ BYT...), chunk theo heading (~500–800 token, overlap),
  embed, upsert. Idempotent theo hash chunk. Chạy tay, không thuộc luồng runtime.
- Nguyên tắc ranh giới: giống memory — Worker đọc Qdrant trực tiếp, không qua Core/queue.

### 3.3 Model config đa vai trò

`app/agent/llm.py`: `get_llm(role: Literal["orchestrator","vision","clinical","distill"] =
"orchestrator")` → chọn model/temperature theo `settings`:

| Setting | Default | Vai trò |
|---|---|---|
| `ORCHESTRATOR_MODEL` | `google_genai:gemini-3.5-flash` | planning/reconcile/reflect/aggregate |
| `VISION_MODEL` | `google_genai:gemini-3.5-flash` (multimodal) | morphology + diễn giải tool output |
| `CLINICAL_MODEL` | `google_genai:gemini-3.5-flash-lite` | normalize/extract |
| `AGENT_MODEL` (cũ) | giữ nguyên | graph hội thoại cũ + distill |

`get_llm` hiện `@lru_cache` không tham số → đổi thành `@lru_cache` theo `role`.
`model_kwargs` (thinking_level/include_thoughts) hiện đang thêm ở `llm.py` — giữ, cho phép
override theo role.

### 3.4 ChatSource wiring

`sources` (`list[ChatSourceDto]`) đã có trong `MessageMetadataDto` + event `message.done`
(`async-api-doc.md` mục 2) nhưng chưa ai set. Clinical Attribute Agent's `retrieve_evidence`
là nơi đầu tiên sinh `sources` thật → nối vào `_persist_assistant` (`extra.sources`) +
payload `message.done`.

## 4. Orchestrator Agent (3.1)

`app/agent/orchestrator/graph.py` — LangGraph riêng, compile với **cùng checkpointer** như
`agent_graph` (`thread_id = message_id`) để resume `ask_user` giữa chừng hoạt động.

### 4.1 `CaseState` (`app/agent/orchestrator/state.py`)

```python
class ImageRef(BaseModel):        attachment_id: str; url: str; mime: str
class SpecialistTask(BaseModel):  agent: Literal["vision","clinical"]; reason: str; inputs: dict
class CandidateDx(BaseModel):
    label: str; rationale: str
    supporting_evidence: list[str]        # trỏ tới evidence id (vision/clinical/guideline)
    against: list[str] = []
    confidence: float                     # 0..1, calibrated ở reflect
class Conflict(BaseModel):        description: str; evidence_a: str; evidence_b: str; resolution: str | None
class GuidelineEvidence(BaseModel):
    citation_key: str; title: str; snippet: str; url: str | None; relevance: float

class CaseState(TypedDict):
    # ── input
    conversation_id: str
    message_id: str
    user_id: str
    symptoms_raw: str
    image_refs: list[ImageRef]
    memory_context: str | None            # từ memory.retrieve_context (tiền sử user)

    # ── evidence do specialist nạp
    vision_evidence: "VisionReport | None"          # mục 5.3
    clinical_attributes: "ClinicalAttributes | None"  # mục 6.3
    retrieved_guidelines: list[GuidelineEvidence]

    # ── reasoning của Orchestrator
    case_summary: str | None
    task_plan: list[SpecialistTask]
    candidate_diagnoses: list[CandidateDx]
    conflicts: list[Conflict]
    gaps: list[str]                        # thiếu gì (ảnh mờ, thiếu thời gian khởi phát...)
    reflection: str | None
    final_assessment: str | None          # → final_answer của turn

    # ── control + chia sẻ với turn/SSE
    round: int
    outcome: Literal["dispatch","need_more","ready"] | None
    messages: Annotated[list[AnyMessage], add_messages]
    reasoning_trace: list[ReasoningResult]   # tái dùng shape cũ (app/agent/state.py)
    pending_tool: PendingTool | None          # Orchestrator được phép ask_user
```

> `reasoning_trace` DÙNG LẠI `ReasoningResult` (`app/agent/state.py`) — không phát minh
> shape mới — để `_persist_assistant`, `to_dto()`, `memory._reasoning_transcript` chạy
> nguyên xi. Thêm field optional `agent: str | None` vào `ReasoningResult` + `ReasoningStepDto`.

### 4.2 Nodes

| Node | LLM? | Việc | Ghi `CaseState` | SSE |
|---|---|---|---|---|
| `understand_case` | `get_llm("orchestrator")` | Đọc `symptoms_raw` + số ảnh + `memory_context` → tóm tắt ca, phân loại (tổn thương khu trú / lan toả / thay đổi sắc tố / ...), liệt kê `gaps` ban đầu | `case_summary`, `gaps` | 1 reasoning step `agent="orchestrator"` |
| `plan` | yes | Sinh `task_plan`: cần Vision (khi có ảnh), cần Clinical (khi có triệu chứng), thứ tự/ song song | `task_plan` | 1 step, `stepType="default"` |
| `dispatch` | no | Với mỗi task chưa chạy: gọi specialist subgraph (mục 5/6). Fan-out song song bằng `asyncio.gather` (Phase 1 chạy tuần tự) | append vào `vision_evidence`/`clinical_attributes`/`retrieved_guidelines` | specialist tự phát step |
| `collect` | no | Chuẩn hoá + gộp evidence vào `CaseState`, gán id cho từng mảnh evidence (để `supporting_evidence` trỏ tới) | — | (không) |
| `reconcile` | yes | So khớp evidence chéo (vision ↔ clinical ↔ guideline). Sinh/cập nhật `candidate_diagnoses`, `conflicts`, `gaps`. Quyết định `outcome`: `need_more` (còn gap giải được bằng specialist khác / tham số khác) · `ask_user` (gap chỉ user trả lời được) · `ready` | `candidate_diagnoses`, `conflicts`, `gaps`, `outcome` | 1 step; nếu `ask_user` → step `tool_ask` + `choice` |
| `reflect` | yes | 3R (Reason→Reflect→Refine): tự phản biện — evidence có đủ đỡ cho từng dx? có overconfidence? có red flag (melanoma ABCDE, nhiễm trùng lan nhanh, tổn thương niêm mạc...) cần khuyến cáo đi khám gấp? Calibrate `confidence`. | `reflection`, cập nhật `candidate_diagnoses[].confidence`, `gaps` | 1 step `agent="orchestrator"` |
| `aggregate` | yes | Soạn `final_assessment` cho user: 2–3 chẩn đoán phân biệt + độ tin cậy (định tính: "khả năng cao/trung bình"), cơ sở, việc nên làm tiếp, **disclaimer + ngưỡng đi khám**. | `final_assessment` | → `finalize` của turn: `message.delta*` + `message.done` (kèm `sources`) |

### 4.3 Vòng lặp bổ sung bằng chứng + `ask_user` giữa chừng

- `reconcile` → `outcome="need_more"` → back về `plan` (round++). `plan` chỉ thêm task
  **mới/định hướng lại** (vd "chạy lại classifier với crop vùng X", "hỏi clinical về tiền
  sử dị ứng"), không lặp task cũ.
- `reconcile` → cần thông tin từ user → set `pending_tool` (tool `ask_user`, cơ chế
  `requires_wait=True` sẵn có) → route sang **node `tool_wait` DÙNG CHUNG** (import từ
  `app/agent/graph.py` hoặc tách ra `app/agent/common/tool_wait.py`). Turn pause,
  `POST .../questions/{qid}/answer` resume đúng vị trí — y hệt graph cũ.
- Sau resume: câu trả lời user vào `messages` + `clinical_attributes` (qua `collect`), quay
  lại `reconcile`.

### 4.4 Loop guard

`settings.ORCHESTRATOR_MAX_ROUNDS = 3`. Khi `round >= MAX` → ép `outcome="ready"` (giống
`step_count >= MAX` của graph cũ), `aggregate` ghi rõ "kết luận sơ bộ do giới hạn thông
tin".

### 4.5 File

```
app/agent/orchestrator/
├── __init__.py
├── state.py          CaseState + các BaseModel evidence
├── graph.py          build_orchestrator_graph() → compiled graph
├── nodes.py          understand_case / plan / dispatch / collect / reconcile / reflect / aggregate
└── prompts.py        system prompt từng node
```

## 5. Vision Expert Agent (3.2)

`app/agent/vision/graph.py` — subgraph, gọi từ `orchestrator/nodes.py::dispatch`. Không có
checkpointer riêng (chạy tới cùng trong 1 lần dispatch; nếu ảnh không dùng được thì trả
report `usable=False` để Orchestrator `ask_user` xin ảnh mới).

### 5.1 Nodes

| Node | Công cụ | Output |
|---|---|---|
| `quality_assessment` | `vision-service /quality` (blur/exposure/resolution/vùng da hợp lệ) — Phase 1: VLM tự chấm | `quality: {score, issues[], usable}` |
| `lesion_detection` | `vision-service /detect` (YOLO / SAM segmentation) — Phase 1: VLM mô tả vị trí | `lesions: [{bbox, mask_ref, site, area_ratio}]` |
| `morphology_extraction` | **VLM** (`get_llm("vision")`) trên từng crop + feature cổ điển (histogram màu, asymmetry, border irregularity) | mỗi lesion: `{color[], shape, border, texture, distribution, size_mm?}` |
| `disease_classifier` | `vision-service /classify` (ResNet/EfficientNet train HAM10000 / Fitzpatrick17k / Derm7pt; hoặc model da liễu chuyên biệt) | `classifier_topk: [{label, prob}]` — **là evidence, không phải verdict** |
| `visual_report` | VLM tổng hợp toàn bộ output tool → clinical representation | `VisionReport` (mục 5.3) |

Mỗi node phát 1 `reasoning.step_*` với `agent="vision"`, `title` kiểu "Đánh giá chất lượng
ảnh", "Trích xuất hình thái tổn thương".

### 5.2 VLM diễn giải, không thay thế tool

`morphology_extraction` / `visual_report` KHÔNG được tự bịa nhãn bệnh khi thiếu output
`disease_classifier`. Prompt ép: "Chỉ mô tả những gì quan sát/đo được; nhãn bệnh chỉ nhắc
lại từ `classifier_topk` kèm độ tin cậy." → giữ đúng vai trò "VLM diễn giải output".

### 5.3 Output — `VisionReport`

```python
class LesionMorphology(BaseModel):
    site: str; color: list[str]; shape: str; border: str; texture: str
    distribution: str; size_mm: float | None; asymmetry: bool | None
class VisionReport(BaseModel):
    usable: bool
    quality_issues: list[str]
    lesion_count: int
    lesions: list[LesionMorphology]
    classifier_topk: list[dict]        # [{label, prob}] — evidence thô
    narrative: str                     # mô tả lâm sàng bằng lời, cho Orchestrator đọc
    evidence_ids: list[str]            # do collect gán
```

### 5.4 MVP (Phase 1) — VLM-only

`vision-service` chưa có → cả 5 node do `get_llm("vision")` multimodal đảm nhiệm (Gemini
nhận `image_url`/inline bytes). `classifier_topk` = "gợi ý sơ bộ của VLM" (đánh dấu
`source="vlm_tentative"`). Phase 2 thay dần bằng model thật, interface `VisionReport` không
đổi.

### 5.5 File

```
app/agent/vision/
├── __init__.py
├── graph.py           build_vision_graph()
├── nodes.py
├── image_loader.py    load bytes từ storage (Phase 0)
├── clients.py         HTTP client tới vision-service (Phase 2)
└── prompts.py
vision-service/         (Phase 2 — repo/dir riêng, FastAPI + torch)
```

## 6. Clinical Attribute Agent (3.3)

`app/agent/clinical/graph.py` — subgraph. Tập trung **patient-side evidence**, không đụng
ảnh.

### 6.1 Nodes

| Node | LLM? | Việc | Output |
|---|---|---|---|
| `normalize_terminology` | `get_llm("clinical")` | Lay VN → thuật ngữ y khoa. "ngứa nhiều về đêm" → `pruritus{severity:high, temporal:nocturnal}` | `terms: [{concept, value, raw_span}]` |
| `extract_attributes` | yes | Onset, duration, temporal pattern, severity (thang 0–3), phân bố giải phẫu, triệu chứng kèm, yếu tố khởi phát/giảm, thuốc/sản phẩm đã dùng, dị ứng | `ClinicalAttributes` (mục 6.3) |
| `differential_clues` | yes | Rút đặc điểm phân biệt: "nocturnal pruritus + đường hầm + lây trong nhà → ghẻ cao trong DDx" — **clue, không phải chẩn đoán** | `clues: list[str]` |
| `retrieve_evidence` | no (embed + search) | Ghép `attributes + clues (+ vision narrative nếu có)` → query text → `search_guidelines` (Qdrant) → passage + citation | `retrieved_guidelines: list[GuidelineEvidence]` |

Mỗi node phát step `agent="clinical"`.

### 6.2 RAG = evidence provider

- Query build từ **structured attributes**, không phải câu user thô → retrieval trúng hơn.
- Kết quả là `GuidelineEvidence` (snippet + `citation_key` + `url`) → chảy vào
  `CaseState.retrieved_guidelines` và cuối cùng thành `message.done.sources`.
- `retrieve_evidence` KHÔNG gọi LLM để "kết luận" — chỉ lấy passage. Việc đối chiếu
  evidence ↔ chẩn đoán là của Orchestrator `reconcile`/`reflect`.
- Tái dùng `memory.retrieve_context(user_id, ...)` cho tiền sử user (đã có) → nạp vào
  `extract_attributes` như context.

### 6.3 Output — `ClinicalAttributes`

```python
class ClinicalAttributes(BaseModel):
    chief_complaint: str
    onset: str | None; duration: str | None
    temporal_pattern: str | None          # nocturnal / intermittent / progressive...
    severity: int | None                  # 0..3
    body_sites: list[str]
    associated_symptoms: list[str]
    triggers: list[str]; relieving_factors: list[str]
    prior_treatments: list[str]; allergies: list[str]
    differential_clues: list[str]
    normalized_terms: list[dict]
    evidence_ids: list[str]
```

### 6.4 File

```
app/agent/clinical/
├── __init__.py
├── graph.py           build_clinical_graph()
├── nodes.py
├── retrieval.py       build query + search_guidelines
└── prompts.py
scripts/ingest_guidelines.py   (Phase 0)
```

## 7. Tracing / SSE / persist

### 7.1 Thêm field `agent` (thay đổi hợp đồng — additive, optional)

- `ReasoningResult` (`app/agent/state.py`): `+ agent: str | None = None`
  (`"orchestrator"|"vision"|"clinical"` — `None` = graph hội thoại cũ).
- `ReasoningStepDto` (`app/dto/message.py`): `+ agent: str | None = None`.
- `worker.py::_publish_reasoning` + `graph.py::_run_llm` writer payload: thêm `"agent"`.
- `async-api-doc.md` mục 2 (bảng `reasoning.step_*`), `asyncapi.yaml`: thêm `agent?`.
- FE `fe/features/chat/types.ts` `ReasoningStep` + `FlatStreamEvent`: `agent?: string`;
  `ReasoningSection.tsx` nhóm/gán badge theo `agent`.
- `openapi.yaml` regen.

### 7.2 Persist + memory

- `orchestrator/graph.py` kết thúc → `worker.py::_drive_graph` lấy `state["reasoning_trace"]`
  (thay `_all_reasoning`) → `_persist_assistant(content=final_assessment, status="done",
  reasoning=trace)` + `extra.sources = retrieved_guidelines`.
- `memory.distill_and_store`: `_reasoning_transcript` đã xử lý `tool_call`/`tool_ask`/text —
  hoạt động với trace multi-agent không cần đổi; chỉ thêm dòng nguồn guideline vào prompt
  distill nếu muốn.

## 8. Worker + triage + resume

`app/agent/worker.py`:

```python
def _triage(req: TurnRequest) -> Literal["chat", "case"]:
    if req.image_refs:                       # có ảnh → chắc chắn là case
        return "case"
    # rẻ: 1 lần gọi LLM lite phân loại "câu hỏi chung" vs "mô tả tình trạng da của tôi"
    return _classify_intent(req.content)     # cache theo hash(content)
```

- `_on_message`: `resume` → nhìn checkpoint xem thread thuộc graph nào (lưu `graph_kind`
  vào `TurnRequest`/Redis khi tạo turn) → drive đúng graph.
- `_drive_graph(req, graph, input_or_command, published)` — tham số hoá `graph` +
  cách lấy trace (`state["reasoning_trace"]` cho orchestrator, `_all_reasoning(state)` cho
  chat). `interrupt()`/`Command(resume=...)`/`stream_mode=["values","custom"]` dùng chung.
- `_initial_case_state(req)`: load memory context + `load_images(req.image_refs)` + set
  `symptoms_raw=req.content`.
- **Checkpointer**: orchestrator có `ask_user` giữa chừng → `InMemorySaver` hiện tại **chặn
  multi-worker**. Ghi nhận: cần Postgres/Redis checkpointer trước khi scale (đã là nợ kỹ
  thuật của graph cũ — `kien-truc-agent.md` mục 7).

## 9. Cấu trúc file mới (tổng hợp)

```
core/app/agent/
├── graph.py                  (giữ; export node tool_wait dùng chung)
├── llm.py                    (get_llm(role=...))
├── worker.py                 (triage, _drive_graph tham số hoá)
├── common/tool_wait.py       (tách node tool_wait để orchestrator import)
├── orchestrator/  { state, graph, nodes, prompts }
├── vision/        { graph, nodes, image_loader, clients, prompts }
├── clinical/      { graph, nodes, retrieval, prompts }
core/app/infra/
├── qdrant_client.py          (+ derma_guidelines collection/search)
├── storage_client.py         (mới — MinIO/local blob)
core/app/api/attachment_api.py (mới — POST .../attachments)
core/app/services/attachment_service.py
core/scripts/ingest_guidelines.py
vision-service/                (Phase 2)
bench/                         (eval — mục 11)
```

## 10. Lộ trình

| Phase | Nội dung | Định nghĩa "xong" |
|---|---|---|
| **0. Prerequisite** | Upload ảnh + storage; collection `derma_guidelines` + `ingest_guidelines.py`; `get_llm(role)`; `sources` nối vào persist/`message.done` | Gửi được tin nhắn kèm ảnh, worker đọc được bytes; query thử `search_guidelines` ra passage |
| **1. Skeleton multi-agent (LLM/VLM-only)** | `orchestrator_graph` đủ 7 node; `vision_graph`/`clinical_graph` chạy bằng VLM/LLM; triage; field `agent` trên SSE + FE badge | FE thấy trace: Orchestrator → Vision → Clinical → reconcile → reflect → assessment cho 1 ca có ảnh + triệu chứng |
| **2. Specialist tools thật** | `vision-service` (quality/detect/classify); Clinical RAG tuning; `classifier_topk` từ model thật | Vision Expert dùng ≥ 1 model thật; `sources` là guideline thật có citation |
| **3. Reflection + conflict loop** | 3R hoàn chỉnh; re-dispatch khi mâu thuẫn; calibrate confidence; red-flag/escalation rules; `bench/` đo top-1/top-3 | Có số liệu accuracy trên tập ca gán nhãn; loop có hard cap, không treo |
| **4. Ops** | dispatch song song; cache kết quả specialist theo hash(ảnh/triệu chứng); Celery; budget latency/cost/turn | p95 latency & cost/turn trong ngưỡng đặt ra |

## 11. Giới hạn đã biết / rủi ro / quyết định cần chốt

**Rủi ro**
- **Latency & cost**: 1 ca = nhiều lần gọi LLM (7 node orchestrator + ~9 node specialist +
  vòng lặp). Bắt buộc: dispatch song song (Phase 4), model lite cho node phân loại/normalize,
  cache, `MAX_ROUNDS` chặt.
- **An toàn y khoa**: không được trình bày như chẩn đoán xác định. `aggregate` bắt buộc có
  disclaimer + ngưỡng "đi khám ngay" (red flags trong `reflect`). Cần review với người có
  chuyên môn trước khi bật cho user thật.
- **Chất lượng RAG** phụ thuộc corpus guideline (VN vs EN, độ cập nhật). Ingestion là công
  đoạn thủ công, chất lượng chunk ảnh hưởng lớn.
- **Model da liễu chuyên biệt**: chọn dataset/model nào (HAM10000 = u sắc tố; Fitzpatrick17k
  = đa dạng tông da; Derm7pt = 7-point checklist)? Licensing? — mở, quyết ở Phase 2.
- **Triage sai** (ca bị coi là chat thường) → thiếu đánh giá. Cần log + cho user nút "phân
  tích kỹ tình trạng da".
- **SSE volume**: nhiều reasoning step → FE cần gộp theo `agent` (accordion) kẻo rối.
- **Checkpointer `InMemorySaver`**: orchestrator pause `ask_user` giữa chừng càng làm nợ này
  gắt hơn — cần checkpointer bền vững trước khi chạy > 1 worker.

**Quyết định cần chốt với chủ nhiệm đề tài trước khi vào Phase 1**
1. **Phạm vi MVP**: đồng ý Phase 1 chạy VLM-only (chưa cần model ML thật)? — *đề xuất: có*.
2. **Coexist qua triage** vs orchestrator cho mọi turn? — *đề xuất: coexist*.
3. **Vision models = service riêng** (`vision-service`) vs nhúng vào worker? — *đề xuất:
   service riêng*.
4. **Storage ảnh**: MinIO (giống hạ tầng hiện có) vs local dir cho dev? — *đề xuất: MinIO*.
5. **Ngôn ngữ corpus guideline** ưu tiên (VN / EN / cả hai) và nguồn được phép dùng.
6. Model đích cho `disease_classifier` ở Phase 2.
