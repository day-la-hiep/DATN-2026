# Plan xây dựng hệ thống Multi-Agent hỗ trợ tư vấn & chẩn đoán bệnh da liễu

> Tài liệu thiết kế cấp kiến trúc cho phần **chatbot đa tác nhân (multi-agent)** của đề tài
> *"Hệ thống quản lý phòng khám da liễu tích hợp chatbot hỗ trợ chẩn đoán dựa trên thị giác
> máy tính, đồ thị tri thức và RAG"*.
>
> Tài liệu liên quan:
> - [`overview/overview.tex`](overview/overview.tex) — xác định đề tài, mục đích, nội dung (CNN+Transformer, CRKG, RAG, Fusion).
> - [`DOAN_BAIBAO_6-2026/dermatology_chatbot_roadmap.md`](DOAN_BAIBAO_6-2026/dermatology_chatbot_roadmap.md) — roadmap mở rộng 7 bệnh → hàng trăm bệnh.
> - `../derma_hospital/core/docs/plans/multi-agent-orchestrator.md` — **plan triển khai code chi tiết** (LangGraph, file layout, SSE contract). Tài liệu này là lớp thiết kế phía trên, plan đó là lớp thực thi.
> - `../derma_hospital/core/app/kien-truc-agent.md` — mô hình Turn / Step / Reasoning và hợp đồng SSE.
> - `../derma_hospital/docs/kien-truc-he-thong.md` — kiến trúc tổng thể Core ↔ Agent Worker ↔ Redis/RabbitMQ.
> - `docs/agent/` — DermAgent (self-reflective agentic system), `derm_3r.pdf` (Reason–Reflect–Refine), "Principles… AI in dermatology".

---

## 1. Mục tiêu & phạm vi

### 1.1 Mục tiêu

Xây dựng một hệ thống **multi-agent** đóng vai trò "hội chẩn ảo": một **Orchestrator** điều phối
nhiều **agent chuyên môn** (vision, lâm sàng, tri thức, an toàn), mỗi agent đóng góp **bằng
chứng có cấu trúc + truy vết được**, và Orchestrator tổng hợp thành **tư vấn kèm chẩn đoán
phân biệt, độ tin cậy, nguồn dẫn và ngưỡng đi khám**.

Hệ thống phải:

1. Nhận **ảnh tổn thương da** và/hoặc **mô tả triệu chứng bằng tiếng Việt**.
2. Suy luận **có giải trình** (Explainable AI): mỗi kết luận phải chỉ ra được đã dựa trên bằng
   chứng nào (ảnh, triệu chứng, guideline, tiền sử).
3. Kết hợp 3 nguồn tri thức bổ trợ: **CNN/Transformer (ảnh)** + **Clinical Reasoning Knowledge
   Graph (CRKG)** + **RAG (guideline y khoa)**, cộng thêm **tiền sử bệnh án** từ module Core.
4. **An toàn y khoa**: không trình bày như chẩn đoán xác định; luôn có disclaimer + phát hiện
   red flag + ngưỡng chuyển bác sĩ.
5. **Mở rộng được**: từ 7 bệnh HAM10000 lên hàng trăm bệnh mà không phải viết lại logic
   (thêm node CRKG + tài liệu RAG, không thêm rule cứng).
6. **Coexist**: hội thoại thông thường ("kem chống nắng nào tốt?") vẫn chạy graph chat đơn
   giản; chỉ **ca da liễu** (có ảnh HOẶC mô tả tình trạng da) mới kích hoạt multi-agent.

### 1.2 Ngoài phạm vi (giai đoạn này)

- Chẩn đoán xác định thay bác sĩ; kê đơn tự động.
- Xử lý video/dermoscopy stream thời gian thực.
- Fine-tune LLM riêng (dùng model có sẵn qua API + model ảnh chuyên biệt self-host).

### 1.3 Nguyên tắc thiết kế (chốt trước khi code)

| # | Nguyên tắc | Hệ quả |
|---|---|---|
| 1 | **Orchestrator điều phối, KHÔNG phải nguồn chân lý y khoa** | Mọi "bằng chứng" đến từ specialist + RAG + KG, không từ prompt Orchestrator |
| 2 | **Specialist = subgraph có trace riêng, KHÔNG phải "tool đục"** | Mỗi bước specialist phát `reasoning.step_*` (kèm nhãn `agent`) ra SSE — giữ tính truy vết |
| 3 | **RAG = evidence provider** | Query RAG chạy *sau* khi có clinical attributes có cấu trúc; trả về passage + citation, không trả về "bệnh X" |
| 4 | **VLM diễn giải output tool, không thay tool** (triết lý DermAgent) | Vision Expert dùng model phân loại/segmentation thật; VLM chỉ mô tả & tổng hợp |
| 5 | **Giữ nguyên hợp đồng SSE Turn/Step/Reasoning** | Chỉ **thêm 1 field optional `agent`** trên reasoning event; không đổi máy trạng thái turn |
| 6 | **Model ảnh chạy ở service riêng (GPU)** | Agent Worker không nhúng torch/YOLO; gọi HTTP tới `vision-service` |
| 7 | **Safety là lớp bắt buộc, không optional** | Red-flag check + disclaimer là node cứng trong graph, không phụ thuộc LLM tự nhớ |
| 8 | **Có vòng lặp bổ sung bằng chứng (3R)** nhưng **có hard cap** | `MAX_ROUNDS` chặt để không treo / không đội chi phí |

---

## 2. Kiến trúc tổng thể

### 2.1 Vị trí trong hệ thống

```
Frontend (Next.js)
   │  REST + SSE  (/api/v1/conversations/{id}/...)
   ▼
Core (FastAPI)  ──publish turn──▶  RabbitMQ agent_request_queue
   ▲                                        │
   │ subscribe & forward nguyên văn         ▼
Redis Pub/Sub  ◀── agent:events:{cid} ──  Agent Worker (LangGraph)
                                            │  _triage(turn)
                             ┌──────────────┴───────────────┐
                     "chat"  │                              │  "case" (có ảnh / mô tả da)
                             ▼                              ▼
                   agent_graph (cũ, giữ nguyên)   orchestrator_graph  ◀── checkpointer
```

Chỉ **thêm** `orchestrator_graph` + các specialist subgraph vào Agent Worker. Core, hợp đồng
REST/SSE, cơ chế persist qua `agent_response_queue` **không đổi** (chỉ thêm field `agent` +
wiring `sources`).

### 2.2 Sơ đồ multi-agent

```
                        ┌─────────────────────────────────────────────────┐
                        │              ORCHESTRATOR  (3.1)                 │
                        │  understand_case → plan → dispatch → collect     │
                        │       → reconcile → reflect(3R) → aggregate      │
                        │            │        ▲           │                │
                        │            │        └─ need_more (round++) ──┐    │
                        │            │        └─ ask_user (interrupt) ─┤    │
                        └────────────┼─────────────────────────────────┼────┘
             dispatch fan-out ───────┼─────────────────────────────────┘
        ┌───────────────┬────────────┼───────────────┬────────────────────┐
        ▼               ▼            ▼               ▼                    ▼
 ┌────────────┐  ┌─────────────┐  ┌──────────┐  ┌────────────┐   ┌──────────────┐
 │  VISION    │  │  CLINICAL   │  │ KNOWLEDGE│  │  PATIENT   │   │   SAFETY     │
 │  EXPERT    │  │  ATTRIBUTE  │  │  GRAPH   │  │  HISTORY   │   │  (Red-flag)  │
 │  (3.2)     │  │  AGENT (3.3)│  │  AGENT   │  │  AGENT     │   │              │
 │            │  │             │  │  (3.4)   │  │  (3.5)     │   │   (3.6)      │
 │ quality →  │  │ normalize → │  │ map      │  │ đọc EMR    │   │ ABCDE / lan  │
 │ lesion →   │  │ extract →   │  │ entities │  │ (Core):    │   │ nhanh / mủ / │
 │ morphology │  │ clues →     │  │ → CRKG   │  │ tiền sử,   │   │ niêm mạc /   │
 │ → classifier│ │ retrieve    │  │ traverse │  │ xét nghiệm,│   │ toàn thân    │
 │ → report   │  │ (RAG)       │  │ → scored │  │ thuốc, dị  │   │ → escalate   │
 │            │  │             │  │ candidates│ │ ứng        │   │              │
 └─────┬──────┘  └──────┬──────┘  └────┬─────┘  └─────┬──────┘   └──────┬───────┘
       │ HTTP           │ Qdrant       │ Neo4j /      │ REST nội bộ     │ rule + KG
       ▼                ▼ derma_        ▼ NetworkX     ▼ Core            ▼
 vision-service    guidelines      CRKG store    EMR / hồ sơ      RedFlag/ReferralRule
 (FastAPI, GPU)    (collection)                  bệnh án          nodes trong CRKG
 /quality /detect /classify

        ┌───────────────────────── FUSION LAYER (3.7) ─────────────────────────┐
        │  Score(d) = w1·P_cnn(d) + w2·P_graph(d) + w3·P_rag(d) + w4·P_history(d) │
        │  (là bước bên trong reconcile/reflect của Orchestrator, không phải     │
        │   agent riêng — nhận evidence đã chuẩn hoá, xuất disease ranking)      │
        └──────────────────────────────────────────────────────────────────────┘

  Mọi node → get_stream_writer() → Redis agent:events:{cid} → SSE (kèm nhãn agent)
  reasoning_trace tích luỹ → agent_response_queue (persist) + memory.distill_and_store
```

### 2.3 Ánh xạ 3 phương pháp AI → agent

| Phương pháp (overview.tex) | Agent phụ trách | Vai trò trong quyết định |
|---|---|---|
| CNN + Transformer phân loại ảnh | **Vision Expert** (§3.2) | `P_cnn(d)` — xác suất bệnh từ ảnh; **là evidence, không phải verdict** |
| Clinical Reasoning Knowledge Graph | **Knowledge Graph Agent** (§3.4) | `P_graph(d)` — điểm khớp triệu chứng↔bệnh theo quan hệ có trọng số; sinh câu hỏi phân biệt |
| RAG (FAISS/Qdrant + guideline) | **Clinical Attribute Agent** (§3.3, node `retrieve_evidence`) | passage + citation ủng hộ/bác bỏ từng ứng viên; nguồn cho `sources` |
| Tiền sử bệnh án (Core EMR) | **Patient History Agent** (§3.5) | `P_history(d)` — điều chỉnh điểm theo tiền sử, xét nghiệm, đáp ứng điều trị trước |
| Fusion + Explanation | **Orchestrator** `reconcile`/`reflect`/`aggregate` (§3.1, §3.7) | tổng hợp có trọng số + giải trình + calibrate confidence + red flag |

---

## 3. Đặc tả từng agent

### 3.1 Orchestrator Agent

**Không tự chẩn đoán.** LangGraph riêng (`app/agent/orchestrator/graph.py`), compile với **cùng
checkpointer** như graph chat (`thread_id = message_id`) để resume `ask_user` giữa chừng.

| Node | LLM | Việc | SSE step (`agent="orchestrator"`) |
|---|---|---|---|
| `understand_case` | orchestrator | Đọc `symptoms_raw` + số ảnh + `memory_context` → tóm tắt ca, phân loại sơ bộ (tổn thương khu trú / lan toả / thay đổi sắc tố / viêm / nhiễm trùng…), liệt kê `gaps` ban đầu | "Tóm tắt ca bệnh" |
| `plan` | orchestrator | Sinh `task_plan`: cần Vision? (có ảnh) cần Clinical? (có triệu chứng) cần History? (user đã đăng nhập & có hồ sơ) — thứ tự & song song | "Lập kế hoạch hội chẩn" |
| `dispatch` | — | Với mỗi task chưa chạy → gọi specialist subgraph; fan-out song song (`asyncio.gather`), Phase 1 chạy tuần tự | (specialist tự phát step) |
| `collect` | — | Chuẩn hoá + gộp evidence vào `CaseState`; **gán id cho từng mảnh evidence** để `supporting_evidence` trỏ tới | — |
| `reconcile` | orchestrator | **Fusion + đối chiếu chéo** (vision ↔ clinical ↔ KG ↔ guideline ↔ history). Sinh/cập nhật `candidate_diagnoses`, `conflicts`, `gaps`. Quyết `outcome`: `need_more` / `ask_user` / `ready` | "Đối chiếu bằng chứng" (+ `tool_ask` nếu hỏi user) |
| `reflect` | orchestrator | **3R (Reason→Reflect→Refine)**: evidence có đủ đỡ mỗi dx? overconfidence? có red flag? Calibrate `confidence`. Gọi Safety Agent nếu chưa chạy | "Tự phản biện & kiểm tra an toàn" |
| `aggregate` | orchestrator | Soạn `final_assessment`: 2–3 chẩn đoán phân biệt + độ tin cậy định tính ("khả năng cao / trung bình / thấp") + cơ sở + việc nên làm tiếp + **disclaimer + ngưỡng đi khám** | → `message.delta*` + `message.done` (kèm `sources`) |

**Vòng lặp bổ sung bằng chứng:**
- `reconcile → need_more` → về `plan` (round++). `plan` chỉ thêm task **mới/định hướng lại**
  ("chạy lại classifier với crop vùng X", "hỏi KG câu phân biệt ghẻ vs eczema"), không lặp task cũ.
- `reconcile` cần thông tin từ user → set `pending_tool` (`ask_user`, `requires_wait=True`) →
  route sang node `tool_wait` **dùng chung** với graph chat → turn pause →
  `POST .../questions/{qid}/answer` resume đúng vị trí.
- **Loop guard:** `settings.ORCHESTRATOR_MAX_ROUNDS = 3`. Chạm ngưỡng → ép `outcome="ready"`,
  `aggregate` ghi rõ "kết luận sơ bộ do giới hạn thông tin".

**`CaseState`** (rút gọn — chi tiết ở plan triển khai):
```python
class CaseState(TypedDict):
    conversation_id: str; message_id: str; user_id: str
    symptoms_raw: str; image_refs: list[ImageRef]; memory_context: str | None
    # evidence do specialist nạp
    vision_evidence: VisionReport | None
    clinical_attributes: ClinicalAttributes | None
    kg_result: KGReasoningResult | None
    history_evidence: HistoryEvidence | None
    retrieved_guidelines: list[GuidelineEvidence]
    safety_flags: list[RedFlag]
    # reasoning của Orchestrator
    case_summary: str | None
    task_plan: list[SpecialistTask]
    candidate_diagnoses: list[CandidateDx]   # label, rationale, supporting/against, confidence
    conflicts: list[Conflict]
    gaps: list[str]
    reflection: str | None
    final_assessment: str | None
    # control + chia sẻ với turn/SSE (tái dùng shape cũ)
    round: int
    outcome: Literal["dispatch","need_more","ready"] | None
    messages: Annotated[list[AnyMessage], add_messages]
    reasoning_trace: list[ReasoningResult]   # + field optional `agent`
    pending_tool: PendingTool | None
```

### 3.2 Vision Expert Agent

`app/agent/vision/graph.py` — subgraph, không checkpointer riêng (chạy tới cùng trong 1 dispatch;
ảnh không dùng được → trả `usable=False` để Orchestrator `ask_user` xin ảnh mới).

| Node | Công cụ (Phase 2) | Phase 1 (VLM-only) | Output |
|---|---|---|---|
| `quality_assessment` | `vision-service /quality` (blur / phơi sáng / độ phân giải / có phải vùng da) | VLM tự chấm | `{score, issues[], usable}` |
| `lesion_detection` | `vision-service /detect` (YOLO / SAM segmentation) | VLM mô tả vị trí | `[{bbox, mask_ref, site, area_ratio}]` |
| `morphology_extraction` | **VLM** (`get_llm("vision")`) trên từng crop + feature cổ điển (histogram màu, asymmetry, độ bất thường viền) | như Phase 2 | mỗi lesion: `{color[], shape, border, texture, distribution, size_mm?, asymmetry}` |
| `disease_classifier` | `vision-service /classify` (ResNet/EfficientNet/CNN+Transformer train HAM10000 / Fitzpatrick17k / Derm7pt) | "gợi ý sơ bộ VLM", đánh dấu `source="vlm_tentative"` | `classifier_topk: [{label, prob}]` — **evidence, không phải verdict** |
| `visual_report` | VLM tổng hợp toàn bộ output tool → clinical representation | như Phase 2 | `VisionReport` |

**Ràng buộc:** `morphology_extraction` / `visual_report` **không được tự bịa nhãn bệnh** khi
thiếu `disease_classifier`. Prompt ép: "Chỉ mô tả những gì quan sát/đo được; nhãn bệnh chỉ nhắc
lại từ `classifier_topk` kèm độ tin cậy." → giữ đúng triết lý DermAgent (VLM diễn giải, không
làm toàn bộ vision reasoning).

```python
class VisionReport(BaseModel):
    usable: bool
    quality_issues: list[str]
    lesion_count: int
    lesions: list[LesionMorphology]      # site, color[], shape, border, texture, distribution, size_mm
    classifier_topk: list[dict]          # [{label, prob, source}]
    narrative: str                       # mô tả lâm sàng bằng lời cho Orchestrator
    evidence_ids: list[str]
```

### 3.3 Clinical Attribute Agent

`app/agent/clinical/graph.py` — patient-side evidence, **không đụng ảnh**.

| Node | LLM | Việc | Output |
|---|---|---|---|
| `normalize_terminology` | clinical (lite) | Lời VN → thuật ngữ y khoa. "ngứa nhiều về đêm" → `pruritus{severity:high, temporal:nocturnal}` | `terms: [{concept, value, raw_span}]` |
| `extract_attributes` | clinical | Onset, duration, temporal pattern, severity (0–3), phân bố giải phẫu, triệu chứng kèm, yếu tố khởi phát/giảm, thuốc/sản phẩm đã dùng, dị ứng | `ClinicalAttributes` |
| `differential_clues` | clinical | Rút đặc điểm phân biệt: "nocturnal pruritus + đường hầm + lây trong nhà → ghẻ cao trong DDx" — **clue, không phải chẩn đoán** | `clues: list[str]` |
| `retrieve_evidence` | — (embed + search) | Ghép `attributes + clues (+ vision narrative nếu có)` → query text → `search_guidelines` (Qdrant `derma_guidelines`) → passage + citation | `retrieved_guidelines: list[GuidelineEvidence]` |

**RAG = evidence provider:** query build từ **structured attributes** (không phải câu user thô)
→ retrieval trúng hơn. Kết quả là `GuidelineEvidence` (snippet + `citation_key` + `url`) → chảy
vào `CaseState.retrieved_guidelines` → cuối cùng thành `message.done.sources`. `retrieve_evidence`
**không gọi LLM để "kết luận"** — chỉ lấy passage; đối chiếu evidence↔dx là việc của Orchestrator.

### 3.4 Knowledge Graph Agent (CRKG)

`app/agent/kg/graph.py` — suy luận trên **Clinical Reasoning Knowledge Graph** (6 lớp: ontology
/ diagnostic reasoning / safety / conversation / evidence / personalization — xem overview.tex).

| Node | Việc | Output |
|---|---|---|
| `map_entities` | Ánh xạ `ClinicalAttributes` + `VisionReport.lesions` vào node CRKG (Symptom, VisualFeature, BodyArea, Duration, Trigger, MedicalHistory…) | `matched_nodes: list[NodeRef]` |
| `traverse` | Từ node đã map, đi theo cạnh `typicalSymptom` / `commonLocation` / `hasRisk` (có trọng số + `evidence_level`) → tập `disease candidates` | `candidates: [{disease, matched_edges, raw_score}]` |
| `score` | Tính `P_graph(d)` = f(số triệu chứng khớp, trọng số cạnh, độ đặc hiệu, `severityRule`) | `graph_scores: dict[disease, float]` |
| `ask_more` | Với ứng viên sát điểm nhau → lấy `Disease ──askMore──▶ Question` để sinh câu hỏi phân biệt cho Orchestrator | `differential_questions: list[str]` |
| `check_graph_safety` | Duyệt `Disease ──redFlag──▶ RedFlag` và `──requiresReferral──▶ ReferralRule` của top ứng viên | `kg_red_flags: list[RedFlag]` |

```python
class KGReasoningResult(BaseModel):
    candidates: list[dict]                 # [{disease, score, matched_edges[], evidence_level}]
    differential_questions: list[str]
    kg_red_flags: list[str]
    contraindications: list[str]           # từ Disease ──contraindicatedTreatment──▶
    evidence_ids: list[str]
```

**Hạ tầng CRKG:** Neo4j (khuyến nghị) hoặc NetworkX + file JSON (dev). Xây dựng bằng
**LLM-assisted + human-in-the-loop** (overview.tex §CRKG): chuyên gia định nghĩa seed schema →
LLM đề xuất node/edge từ guideline → chuyên gia duyệt → sinh graph. Mỗi cạnh có `confidence`,
`evidence_level`, `source`, `last_reviewed`.

### 3.5 Patient History Agent

`app/agent/history/graph.py` — chỉ chạy khi user đã đăng nhập & Orchestrator `plan` yêu cầu.
Đọc **hồ sơ bệnh án điện tử** từ Core (REST nội bộ hoặc DB read-replica — quyết ở Phase 2).

| Node | Việc | Output |
|---|---|---|
| `fetch_emr` | Lấy: chẩn đoán da liễu trước, kết quả xét nghiệm (KOH, sinh thiết, Wood's lamp, test dị ứng), thuốc đang dùng, phác đồ trước + đáp ứng, dị ứng, bệnh nền, tiền sử gia đình | `emr_snapshot` |
| `reason_history` | Áp luật suy luận: `KOH(+) → giảm eczema, tăng fungal`; `biopsy atypical cells → tăng malignancy`; `retinoid trước không đáp ứng → hạ ứng viên tương ứng`; `tiểu đường → cảnh báo corticosteroid kéo dài` | `history_adjustments: dict[disease, float]` + `contraindication_notes` |

```python
class HistoryEvidence(BaseModel):
    has_emr: bool
    prior_diagnoses: list[str]
    lab_results: list[dict]                # [{test, result, date}]
    treatment_responses: list[dict]        # [{treatment, response}]
    history_adjustments: dict              # disease -> delta điểm (P_history)
    contraindication_notes: list[str]
    evidence_ids: list[str]
```

> **Ranh giới dữ liệu:** Agent Worker đọc EMR **chỉ đọc**, không ghi. Quyền truy cập giới hạn
> theo `user_id` của turn (bệnh nhân chỉ thấy hồ sơ của mình; bác sĩ theo phân quyền Core).

### 3.6 Safety Agent (Red-flag / Escalation)

**Không phải subgraph LLM tự do** — là bộ **rule + tra CRKG** chạy trong `reflect` của
Orchestrator (và có thể chạy sớm ngay sau `collect` nếu ảnh/triệu chứng gợi ý nguy hiểm).

Kiểm tra bắt buộc:
- **Melanoma ABCDE** từ `VisionReport` (asymmetry, border, color ≥ 2, đường kính > 6mm, tiến triển).
- **Nhiễm trùng lan nhanh**: sưng đau tăng nhanh, sốt, chảy mủ, viền lan rộng theo giờ.
- **Tổn thương niêm mạc / quanh mắt / sinh dục**, hội chứng bong da toàn thân (SJS/TEN nghi ngờ).
- **Triệu chứng toàn thân**: sốt cao, khó thở, phù mặt (phản vệ).
- `Disease ──redFlag──▶ RedFlag` và `──requiresReferral──▶ ReferralRule` của top ứng viên CRKG.

Output `safety_flags: list[RedFlag]`; nếu có flag mức cao → `aggregate` **bắt buộc** mở đầu bằng
khuyến cáo đi khám ngay và **hạ tông** phần chẩn đoán phân biệt.

### 3.7 Fusion Layer (trong Orchestrator)

Không phải agent riêng — là phép tính trong `reconcile`/`reflect`:

```
Score(d) = w1·P_cnn(d) + w2·P_graph(d) + w3·P_rag(d) + w4·P_history(d),   Σ wᵢ = 1
```

- `P_cnn`: chuẩn hoá từ `VisionReport.classifier_topk` (0 nếu không có ảnh → phân bổ lại trọng số).
- `P_graph`: từ `KGReasoningResult.candidates[].score`.
- `P_rag`: mức độ guideline ủng hộ/bác bỏ d (LLM `reconcile` chấm định tính rồi map sang [0,1],
  hoặc similarity của passage khớp nhãn d).
- `P_history`: từ `HistoryEvidence.history_adjustments` (mặc định 0.5 khi không có EMR).
- **Trọng số**: khởi tạo `w = (0.4, 0.3, 0.2, 0.1)`; Phase 3 tối ưu trên tập ca gán nhãn
  (grid search / logistic regression trên điểm thành phần). Ghi `w` vào `settings` để cấu hình.
- **Không dùng Fusion như hộp đen**: `aggregate` phải giải thích *"ảnh gợi ý X (prob 0.7),
  triệu chứng + phân bố khớp Y trên CRKG, guideline Z ủng hộ Y, tiền sử không mâu thuẫn"*.

---

## 4. Hạ tầng & dịch vụ mới

| Hạng mục | Công nghệ | Mục đích | Phase |
|---|---|---|---|
| **Upload ảnh** | Endpoint `POST /conversations/{id}/attachments` (multipart) + `AttachmentService` + `storage_client` | Vision cần bytes ảnh thật (hiện `attachments` chỉ có metadata) | 0 |
| **Blob storage** | MinIO (S3-compatible) — thêm vào `docker-compose.yml`; dev có thể dùng `var/uploads/` | Lưu ảnh tổn thương | 0 |
| **KB guideline** | Qdrant collection **`derma_guidelines`** (tách khỏi `agent_memories`), embedding `gemini-embedding-001` @ 768d | RAG evidence | 0 |
| **Ingestion guideline** | `scripts/ingest_guidelines.py` — PDF trong `docs/agent/` + AAD/DermNet/phác đồ BYT, chunk theo heading (~500–800 token, overlap), embed, upsert idempotent | Nạp corpus, chạy tay | 0 |
| **CRKG store** | Neo4j (thêm container) hoặc NetworkX + JSON | Đồ thị suy luận lâm sàng | 1–2 |
| **CRKG builder** | `scripts/build_crkg.py` — LLM-assisted, xuất diff cho chuyên gia duyệt | Mở rộng 7 → hàng trăm bệnh | 2–3 |
| **vision-service** | FastAPI + torch/onnx, self-host GPU; endpoint `/quality` `/detect` `/classify` | Model ảnh chuyên biệt, tách khỏi Worker | 2 |
| **Model config đa vai trò** | `get_llm(role: "orchestrator"\|"vision"\|"clinical"\|"kg"\|"distill")` — `@lru_cache` theo role | Chọn model/temperature theo vai trò | 0 |
| **`sources` wiring** | `retrieve_evidence` sinh `sources` thật → `_persist_assistant(extra.sources)` + `message.done` | Trích dẫn nguồn hiển thị ở FE | 0 |

Mặc định model (điều chỉnh theo chi phí/độ trễ thực tế):

| Setting | Default | Vai trò |
|---|---|---|
| `ORCHESTRATOR_MODEL` | Gemini/Claude flash-tier | planning / reconcile / reflect / aggregate |
| `VISION_MODEL` | model multimodal | morphology + diễn giải output tool |
| `CLINICAL_MODEL` | model lite | normalize / extract |
| `KG_MODEL` | model lite | map_entities / ask_more |
| `AGENT_MODEL` (cũ) | giữ nguyên | graph chat cũ + distill memory |

---

## 5. Tracing / SSE / persist

Chỉ **1 thay đổi hợp đồng, additive & optional**:

- `ReasoningResult` (`app/agent/state.py`): `+ agent: str | None = None`
  (`"orchestrator"|"vision"|"clinical"|"kg"|"history"` — `None` = graph chat cũ).
- `ReasoningStepDto` (`app/dto/message.py`): `+ agent: str | None = None`.
- `worker.py::_publish_reasoning` + writer payload: thêm `"agent"`.
- `async-api-doc.md` / `asyncapi.yaml` / `openapi.yaml`: thêm `agent?` (regen).
- FE `fe/features/chat/types.ts` `ReasoningStep`: `agent?: string`; `ReasoningSection.tsx` gộp
  step theo `agent` (accordion / badge màu theo agent).

Persist: `orchestrator_graph` kết thúc → `worker.py::_drive_graph` lấy `state["reasoning_trace"]`
→ `_persist_assistant(content=final_assessment, status="done", reasoning=trace)` +
`extra.sources = retrieved_guidelines`. `memory.distill_and_store` chạy nguyên xi với trace
multi-agent (đã xử lý `tool_call`/`tool_ask`/text).

Worker triage:
```python
def _triage(req: TurnRequest) -> Literal["chat", "case"]:
    if req.image_refs:                       # có ảnh → chắc chắn là case
        return "case"
    return _classify_intent(req.content)     # 1 lần gọi LLM lite, cache theo hash(content)
```
`_on_message` khi resume: đọc `graph_kind` (lưu vào `TurnRequest`/Redis lúc tạo turn) → drive
đúng graph.

---

## 6. Lộ trình

| Phase | Nội dung | "Xong" khi |
|---|---|---|
| **0. Prerequisite** | Upload ảnh + MinIO; collection `derma_guidelines` + `ingest_guidelines.py`; `get_llm(role)`; `sources` nối persist/`message.done`; field `agent` trên SSE + FE badge | Gửi tin nhắn kèm ảnh, worker đọc được bytes; `search_guidelines` ra passage; FE hiển thị badge agent |
| **1. Skeleton multi-agent (LLM/VLM-only)** | `orchestrator_graph` đủ 7 node; `vision_graph` + `clinical_graph` chạy bằng VLM/LLM; triage; Fusion định tính; disclaimer + red-flag rule tối thiểu | FE thấy trace: Orchestrator → Vision → Clinical → reconcile → reflect → assessment cho 1 ca có ảnh + triệu chứng, kèm disclaimer |
| **2. Specialist tools thật + CRKG** | `vision-service` (`/quality` `/detect` `/classify`) với ≥ 1 model thật (HAM10000); Neo4j + CRKG cho 7 bệnh; `kg_graph`; `history_graph` đọc EMR; RAG guideline thật có citation | Vision Expert dùng model ML thật; `P_graph` từ CRKG; `sources` là guideline thật |
| **3. Reflection + conflict loop + Fusion tuning** | 3R hoàn chỉnh; re-dispatch khi mâu thuẫn; calibrate confidence; red-flag/escalation đầy đủ; tối ưu trọng số Fusion; `bench/` đo top-1/top-3 | Có số liệu accuracy trên tập ca gán nhãn; loop có hard cap, không treo |
| **4. Mở rộng + Ops** | CRKG builder LLM-assisted → hàng trăm bệnh; dispatch song song; cache kết quả specialist theo `hash(ảnh/triệu chứng)`; Celery hoá worker; checkpointer bền vững (Postgres/Redis); budget latency/cost/turn | p95 latency & cost/turn trong ngưỡng; CRKG > 50 bệnh đã duyệt |

---

## 7. Đánh giá (`bench/`)

| Nhóm | Chỉ số | Nguồn dữ liệu |
|---|---|---|
| **Chẩn đoán** | top-1 / top-3 accuracy, balanced accuracy, per-class F1 | HAM10000 test split, ISIC, tập ca gán nhãn nội bộ (ảnh + mô tả) |
| **Vision riêng** | accuracy classifier, AUROC melanoma, tỉ lệ "ảnh không dùng được" bắt đúng | vision-service eval set |
| **RAG** | recall@k của passage đúng chủ đề, tỉ lệ citation hợp lệ, tỉ lệ câu trả lời có ≥ 1 nguồn | bộ câu hỏi y khoa gán nhãn |
| **An toàn** | recall red-flag (melanoma, nhiễm trùng lan nhanh, SJS/TEN) — **ưu tiên cao nhất**, tỉ lệ có disclaimer | ca red-flag tổng hợp + review chuyên gia |
| **Hội thoại** | tỉ lệ hỏi thêm đúng lúc, số vòng trung bình/ca, tỉ lệ chạm `MAX_ROUNDS` | log turn |
| **Vận hành** | p50/p95 latency/turn, số lần gọi LLM/turn, cost/turn | tracing |
| **Truy vết** | tỉ lệ kết luận có `supporting_evidence` trỏ tới evidence id hợp lệ | audit trace |

Quy trình: mỗi Phase khoá 1 tập ca cố định; so sánh **single-agent (graph chat + prompt) vs
multi-agent** để chứng minh giá trị kiến trúc cho báo cáo đề tài.

---

## 8. Rủi ro & quyết định cần chốt

**Rủi ro**

| Rủi ro | Giảm thiểu |
|---|---|
| **Latency & cost**: 1 ca = nhiều lần gọi LLM (7 node orchestrator + ~12 node specialist + vòng lặp) | dispatch song song (Phase 4), model lite cho normalize/classify, cache theo hash, `MAX_ROUNDS = 3` |
| **An toàn y khoa**: trình bày như chẩn đoán xác định | Safety Agent là node cứng; `aggregate` bắt buộc disclaimer + ngưỡng đi khám; review với người có chuyên môn trước khi bật cho user thật |
| **Chất lượng RAG** phụ thuộc corpus (VN vs EN, độ cập nhật) | ưu tiên nguồn uy tín (AAD, DermNet, NHS, phác đồ BYT), chunk theo heading, ghi `citation_key` |
| **CRKG sai / thiên lệch** | mọi cạnh có `evidence_level` + `source` + `last_reviewed`; human-in-the-loop bắt buộc trước khi merge |
| **Model ảnh**: HAM10000 lệch về u sắc tố, ít đa dạng tông da | bổ sung Fitzpatrick17k / Derm7pt ở Phase 2; báo cáo giới hạn |
| **Triage sai** (ca bị coi là chat thường) | log + nút FE "phân tích kỹ tình trạng da" để ép vào orchestrator |
| **SSE volume**: nhiều reasoning step → FE rối | gộp theo `agent` (accordion), chỉ mở agent đang chạy |
| **Checkpointer `InMemorySaver`** chặn multi-worker; orchestrator pause `ask_user` càng gắt | Postgres/Redis checkpointer trước khi chạy > 1 worker (đã là nợ kỹ thuật của graph cũ) |
| **Bảo mật EMR**: Agent Worker đọc hồ sơ bệnh án | chỉ đọc, giới hạn theo `user_id`/phân quyền Core, không log nội dung nhạy cảm |

**Quyết định cần chốt với chủ nhiệm đề tài (trước Phase 1)**

1. Phạm vi MVP: đồng ý Phase 1 chạy **VLM/LLM-only** (chưa cần model ML + CRKG thật)? — *đề xuất: có*.
2. **Coexist qua triage** vs orchestrator cho mọi turn? — *đề xuất: coexist*.
3. Vision models = **service riêng** (`vision-service`) vs nhúng vào worker? — *đề xuất: service riêng*.
4. CRKG store: **Neo4j** vs NetworkX+JSON? — *đề xuất: Neo4j từ Phase 2, JSON cho prototype*.
5. Storage ảnh: **MinIO** vs local dir? — *đề xuất: MinIO*.
6. Ngôn ngữ corpus guideline ưu tiên (VN / EN / cả hai) và nguồn được phép dùng.
7. Model đích cho `disease_classifier` Phase 2 (HAM10000 / Fitzpatrick17k / Derm7pt) & licensing.
8. Patient History Agent đọc EMR qua **REST nội bộ Core** vs **DB read-replica**? — *đề xuất: REST nội bộ*.
9. Trọng số Fusion khởi tạo & có tối ưu bằng dữ liệu ở Phase 3 không.

---

## 9. Cấu trúc file (Agent Worker)

```
core/app/agent/
├── graph.py                  (giữ; export node tool_wait dùng chung)
├── llm.py                    (get_llm(role=...))
├── worker.py                 (triage, _drive_graph tham số hoá theo graph)
├── common/tool_wait.py       (tách node tool_wait để các graph import)
├── orchestrator/  { state.py, graph.py, nodes.py, prompts.py }
├── vision/        { graph.py, nodes.py, image_loader.py, clients.py, prompts.py }
├── clinical/      { graph.py, nodes.py, retrieval.py, prompts.py }
├── kg/            { graph.py, nodes.py, crkg_client.py, prompts.py }
├── history/       { graph.py, nodes.py, emr_client.py }
└── safety/        { rules.py }              # rule-based, không graph
core/app/infra/
├── qdrant_client.py          (+ derma_guidelines collection/search)
├── storage_client.py         (MinIO/local blob)
└── neo4j_client.py           (CRKG)
core/app/api/attachment_api.py + services/attachment_service.py
core/scripts/  { ingest_guidelines.py, build_crkg.py }
vision-service/               (Phase 2 — FastAPI + torch, repo/dir riêng)
bench/                        (eval — §7)
```
