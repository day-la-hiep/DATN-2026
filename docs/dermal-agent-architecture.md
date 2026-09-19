# Kiến trúc Agent — vai trò, hướng dẫn, pipeline & nguồn dữ liệu

> Tài liệu đặc tả **bên trong** hệ thống multi-agent chẩn đoán da liễu: mỗi agent làm gì
> (vai trò), hoạt động theo nguyên tắc nào (hướng dẫn / system prompt), chạy qua các bước
> nào (pipeline), và **mỗi bước lấy dữ liệu từ đâu**.
>
> Xem thêm:
> - [`dermal-multi-agent-plan.md`](dermal-multi-agent-plan.md) — plan cấp hệ thống (hạ tầng, lộ trình, rủi ro).
> - `../derma_hospital/core/app/kien-truc-agent.md` — mô hình Turn / Step / Reasoning + hợp đồng SSE.
> - `docs/agent/` — DermAgent (self-reflective agentic system), `derm_3r.pdf` (Reason–Reflect–Refine).

---

## 1. Bức tranh tổng thể

```
                             ┌──────────────────────────────────────────┐
   Turn (ảnh + text) ───────▶│              ORCHESTRATOR                 │
                             │  điều phối · KHÔNG tự chẩn đoán           │
                             │                                          │
   understand_case ─▶ plan ─▶ dispatch ─▶ collect ─▶ reconcile ─▶ reflect ─▶ aggregate ─▶ trả lời
                             │     │                     │  ▲          │              │
                             │     │                     │  └ need_more (round++)     │
                             │     │                     │  └ ask_user (pause turn)   │
                             └─────┼─────────────────────┼───────────────────────────┘
                    fan-out ───────┤ gọi specialist subgraph
        ┌──────────────┬───────────┼──────────────┬──────────────────┐
        ▼              ▼           ▼              ▼                  ▼
  VISION EXPERT   CLINICAL     KNOWLEDGE      PATIENT           SAFETY
                  ATTRIBUTE    GRAPH          HISTORY           (rule + KG)
                  AGENT        AGENT          AGENT
```

**Quy tắc bất biến:**

1. **Orchestrator điều phối, không phải nguồn chân lý y khoa.** Nó lập kế hoạch, phân việc,
   phát hiện thiếu/mâu thuẫn, tổng hợp. Mọi *bằng chứng* đến từ specialist + KG + RAG + EMR.
2. **Mỗi specialist là subgraph có trace riêng.** Mỗi bước phát `reasoning.step_*` ra SSE kèm
   nhãn `agent` — không bọc specialist thành "một tool đục".
3. **Mỗi mảnh bằng chứng có `evidence_id`.** `collect` gán id; `candidate_diagnoses` chỉ được
   trích dẫn evidence bằng id → mọi kết luận truy vết được về nguồn.
4. **RAG & classifier là *evidence provider*, không phải *người phán quyết*.** Chúng trả về
   passage / xác suất; việc kết luận là của Orchestrator (`reconcile`/`reflect`).
5. **Safety là node cứng**, không phụ thuộc LLM tự nhớ kiểm tra.

---

## 2. Danh mục nguồn dữ liệu (data sources)

Mọi bước trong tài liệu này chỉ được lấy dữ liệu từ các nguồn dưới đây:

| Ký hiệu | Nguồn | Nội dung | Ai đọc | Ghi chú |
|---|---|---|---|---|
| **D1** | `TurnRequest.content` | Mô tả triệu chứng bằng tiếng Việt của user | Orchestrator, Clinical | text thô |
| **D2** | `TurnRequest.image_refs[]` → MinIO blob | Bytes ảnh tổn thương (jpeg/png/webp, ≤ 8MB, ≤ 4 ảnh) | Vision (qua `image_loader`) | verify mime/size, downscale |
| **D3** | `memory.retrieve_context(user_id)` — Qdrant `agent_memories` | Tiền sử hội thoại / ghi chú dài hạn per-user (đã distill) | Orchestrator, Clinical | có sẵn trong hệ thống |
| **D4** | Qdrant `derma_guidelines` | Passage guideline y khoa (AAD, DermNet, NHS, phác đồ BYT…) + `citation_key`, `url` | Clinical (`retrieve_evidence`) | ingestion offline |
| **D5** | CRKG store (Neo4j / NetworkX) | Đồ thị suy luận lâm sàng: Disease–Symptom–VisualFeature–BodyArea–RedFlag–Treatment… với trọng số + `evidence_level` | Knowledge Graph Agent, Safety | 6 lớp (xem overview.tex) |
| **D6** | `vision-service` `/quality` `/detect` `/classify` (HTTP) | Điểm chất lượng ảnh, bbox/mask tổn thương, top-k nhãn bệnh + prob | Vision Expert | Phase 2; Phase 1 = VLM thay thế |
| **D7** | Core EMR (REST nội bộ) | Hồ sơ bệnh án: chẩn đoán trước, xét nghiệm (KOH, sinh thiết, Wood's lamp, test dị ứng), thuốc, phác đồ + đáp ứng, dị ứng, bệnh nền, tiền sử gia đình | Patient History Agent | chỉ đọc, giới hạn theo `user_id` |
| **D8** | `CaseState` (state nội bộ graph) | Evidence do các specialist đã nạp + reasoning của Orchestrator | mọi node | xem §3.1 |
| **D9** | `user` answer qua `POST .../questions/{qid}/answer` | Câu trả lời user cho `ask_user` giữa chừng | Orchestrator (resume) | cơ chế `interrupt()` |

> **Nguyên tắc nguồn:** một bước LLM **chỉ** được suy luận trên dữ liệu truyền vào prompt của
> nó (từ D1–D9). Không được "nhớ" kiến thức y khoa tự do để đưa ra nhãn bệnh — nhãn bệnh phải
> đến từ D5 (CRKG) hoặc D6 (classifier).

---

## 3. Orchestrator Agent

### 3.1 Vai trò

Điều phối một "phiên hội chẩn": hiểu ca bệnh → quyết định cần hỏi chuyên gia nào → thu thập
bằng chứng → phát hiện thiếu/mâu thuẫn → yêu cầu bổ sung hoặc hỏi user → tổng hợp thành tư vấn
cuối. **Không tự đưa ra nhãn bệnh từ kiến thức riêng.**

### 3.2 Nguyên tắc hoạt động (system prompt — rút gọn)

```
Bạn là điều phối viên hội chẩn da liễu. Bạn KHÔNG phải bác sĩ chẩn đoán.
Nhiệm vụ: lập kế hoạch, phân việc cho chuyên gia (Vision / Clinical / KnowledgeGraph /
History), đối chiếu bằng chứng họ trả về, phát hiện chỗ thiếu và mâu thuẫn, rồi tổng hợp.

Ràng buộc:
- Mọi nhận định về bệnh phải trích dẫn evidence_id cụ thể (từ specialist / KG / guideline / EMR).
- Không được tự thêm nhãn bệnh không có trong classifier_topk hoặc kg_result.candidates.
- Nếu thiếu dữ kiện mà chỉ user trả lời được → dùng ask_user, KHÔNG đoán bừa.
- Nếu evidence mâu thuẫn → ghi vào conflicts, tìm cách giải quyết ở vòng sau.
- Luôn gọi kiểm tra an toàn (Safety) trước khi tổng hợp.
- Câu trả lời cuối: chẩn đoán phân biệt (2–3) + độ tin cậy định tính + cơ sở + việc nên làm
  + disclaimer + ngưỡng đi khám. KHÔNG khẳng định chắc chắn.
```

### 3.3 Pipeline

| Bước | Nguồn dữ liệu vào | Xử lý | LLM | Kết quả ra (`CaseState`) |
|---|---|---|---|---|
| **understand_case** | D1 (mô tả), số lượng D2 (đếm ảnh), D3 (memory) | Tóm tắt ca; phân loại sơ bộ (khu trú / lan toả / thay đổi sắc tố / viêm / nhiễm trùng / dị ứng); liệt kê thông tin còn thiếu | `orchestrator` | `case_summary`, `gaps[]` |
| **plan** | D8: `case_summary`, `gaps`, có ảnh?, user đăng nhập? | Sinh `task_plan`: Vision nếu có D2; Clinical nếu có D1; KnowledgeGraph luôn (khi đã có ≥1 triệu chứng); History nếu user có hồ sơ. Xác định chạy song song / tuần tự | `orchestrator` | `task_plan: list[SpecialistTask]` |
| **dispatch** | D8: `task_plan` | Gọi từng specialist subgraph (§4–§7). Fan-out `asyncio.gather` (Phase 1: tuần tự). Không tự suy luận | — | append `vision_evidence` / `clinical_attributes` / `kg_result` / `history_evidence` / `retrieved_guidelines` |
| **collect** | D8: các evidence vừa nạp | Chuẩn hoá schema; **gán `evidence_id`** cho từng mảnh (vd `vis:lesion1`, `kg:cand:acne`, `gl:aad_acne_2024#3`, `emr:koh_pos`) | — | `evidence_index: dict[id, Evidence]` |
| **reconcile** | D8: toàn bộ evidence + `evidence_index` | **Fusion** (`Score(d)=Σ wᵢ·Pᵢ(d)`, §3.5) → disease ranking; đối chiếu chéo vision↔clinical↔KG↔guideline↔history; cập nhật `candidate_diagnoses` (mỗi cái: `supporting_evidence[]`, `against[]`), `conflicts[]`, `gaps[]`. Quyết `outcome` | `orchestrator` | `candidate_diagnoses`, `conflicts`, `gaps`, `outcome` |
| **(ask_user)** | D8: `gaps` mà chỉ user trả lời được | Set `pending_tool=ask_user` → node `tool_wait` `interrupt()` → **turn pause** | — | chờ D9 |
| **reflect** | D8: `candidate_diagnoses`, `conflicts`; D5 red-flag của top ứng viên; Safety Agent (§8) | 3R: Reason (bằng chứng đủ đỡ mỗi dx?) → Reflect (overconfidence? bỏ sót red flag?) → Refine (calibrate `confidence`, thêm `gaps`). Gọi Safety nếu chưa chạy | `orchestrator` | `reflection`, `candidate_diagnoses[].confidence`, `safety_flags` |
| **aggregate** | D8: `candidate_diagnoses` (đã calibrate), `safety_flags`, `retrieved_guidelines` | Soạn `final_assessment` cho user; nếu có `safety_flags` mức cao → mở đầu bằng khuyến cáo đi khám ngay | `orchestrator` | `final_assessment` → `message.delta*` + `message.done` (kèm `sources`) |

### 3.4 Vòng lặp bổ sung bằng chứng

- `reconcile → outcome="need_more"` → quay lại `plan` (`round++`). `plan` chỉ thêm task
  **mới / định hướng lại** ("chạy lại classifier với crop vùng cổ", "hỏi KG câu phân biệt
  ghẻ vs viêm da cơ địa"). **Không lặp task cũ.**
- `reconcile → cần user` → `ask_user` → pause → D9 → câu trả lời vào `messages` +
  `clinical_attributes` (qua `collect`) → quay lại `reconcile`.
- **Hard cap:** `ORCHESTRATOR_MAX_ROUNDS = 3`. Chạm ngưỡng → ép `outcome="ready"`; `aggregate`
  ghi rõ "kết luận sơ bộ do giới hạn thông tin".

### 3.5 Fusion (bên trong `reconcile`)

```
Score(d) = w1·P_cnn(d) + w2·P_graph(d) + w3·P_rag(d) + w4·P_history(d)     Σ wᵢ = 1
```

| Thành phần | Lấy từ | Khi không có nguồn |
|---|---|---|
| `P_cnn(d)` | `vision_evidence.classifier_topk` (D6) chuẩn hoá | = 0, phân bổ lại `w1` sang thành phần khác |
| `P_graph(d)` | `kg_result.candidates[].score` (D5) | = 0 |
| `P_rag(d)` | mức guideline ủng hộ/bác bỏ d — LLM `reconcile` chấm định tính rồi map [0,1] | = 0.5 (trung tính) |
| `P_history(d)` | `history_evidence.history_adjustments[d]` (D7) | = 0.5 (trung tính) |

Trọng số khởi tạo `w = (0.4, 0.3, 0.2, 0.1)`, cấu hình trong `settings`, tối ưu ở Phase 3 trên
tập ca gán nhãn. **Fusion không phải hộp đen:** `aggregate` phải diễn giải bằng lời từng thành
phần đã đóng góp gì.

### 3.6 Contract state (rút gọn)

```python
class CandidateDx(BaseModel):
    label: str
    rationale: str
    supporting_evidence: list[str]   # evidence_id
    against: list[str] = []
    confidence: float                # 0..1, calibrated ở reflect

class Conflict(BaseModel):
    description: str; evidence_a: str; evidence_b: str; resolution: str | None

class CaseState(TypedDict):
    conversation_id: str; message_id: str; user_id: str
    symptoms_raw: str; image_refs: list[ImageRef]; memory_context: str | None
    vision_evidence: "VisionReport | None"
    clinical_attributes: "ClinicalAttributes | None"
    kg_result: "KGReasoningResult | None"
    history_evidence: "HistoryEvidence | None"
    retrieved_guidelines: list["GuidelineEvidence"]
    safety_flags: list["RedFlag"]
    evidence_index: dict[str, "Evidence"]
    case_summary: str | None
    task_plan: list["SpecialistTask"]
    candidate_diagnoses: list[CandidateDx]
    conflicts: list[Conflict]
    gaps: list[str]
    reflection: str | None
    final_assessment: str | None
    round: int
    outcome: Literal["dispatch", "need_more", "ready"] | None
    messages: Annotated[list[AnyMessage], add_messages]
    reasoning_trace: list["ReasoningResult"]   # + field optional `agent`
    pending_tool: "PendingTool | None"
```

---

## 4. Vision Expert Agent

### 4.1 Vai trò

Biến **ảnh tổn thương** thành **biểu diễn lâm sàng có cấu trúc**: chất lượng ảnh → vị trí tổn
thương → hình thái (màu/hình/viền/bề mặt/phân bố) → gợi ý nhãn bệnh từ model → báo cáo. **VLM
diễn giải output của model, không tự làm toàn bộ vision reasoning** (triết lý DermAgent).

### 4.2 Nguyên tắc hoạt động (system prompt — rút gọn)

```
Bạn là chuyên gia phân tích ảnh da liễu. Bạn nhận ảnh + output từ các model thị giác.

Ràng buộc:
- CHỈ mô tả những gì quan sát hoặc đo được trên ảnh (màu, hình dạng, viền, bề mặt, kích thước,
  phân bố, số lượng tổn thương).
- Nhãn bệnh: CHỈ nhắc lại từ classifier_topk (kèm xác suất). KHÔNG tự thêm nhãn khác.
- Nếu ảnh mờ / thiếu sáng / không phải vùng da / không thấy rõ tổn thương → usable=false và
  nêu lý do cụ thể để Orchestrator xin ảnh mới.
- Không suy đoán triệu chứng không nhìn thấy (ngứa, đau, thời gian…) — đó là việc của Clinical.
```

### 4.3 Pipeline

| Bước | Nguồn dữ liệu vào | Xử lý | Công cụ (Phase 2 / Phase 1) | Kết quả ra |
|---|---|---|---|---|
| **quality_assessment** | D2 (bytes ảnh) | Chấm blur / phơi sáng / độ phân giải / có phải vùng da; kết luận `usable` | `/quality` (CNN nhỏ) / VLM tự chấm | `{score, issues[], usable}` |
| **lesion_detection** | D2 | Phát hiện & khoanh vùng tổn thương, ước lượng vị trí giải phẫu, tỉ lệ diện tích | `/detect` (YOLO / SAM) / VLM mô tả vị trí | `lesions: [{bbox, mask_ref, site, area_ratio}]` |
| **morphology_extraction** | D2 crop theo bbox + đặc trưng cổ điển (histogram màu, asymmetry, độ bất thường viền) | Với mỗi tổn thương: trích màu (list), hình dạng, đặc điểm viền, bề mặt, phân bố, kích thước (mm nếu có tham chiếu tỉ lệ) | **VLM** `get_llm("vision")` + OpenCV | mỗi lesion: `LesionMorphology` |
| **disease_classifier** | D2 crop | Phân loại top-k nhãn bệnh + xác suất | `/classify` (ResNet/EfficientNet/CNN+Transformer — HAM10000 / Fitzpatrick17k / Derm7pt) / VLM `source="vlm_tentative"` | `classifier_topk: [{label, prob, source}]` |
| **visual_report** | D8: output 4 bước trên | Tổng hợp thành narrative lâm sàng bằng lời cho Orchestrator; đánh dấu độ chắc chắn của từng quan sát | VLM | `VisionReport` |

Mỗi bước phát 1 `reasoning.step_*` với `agent="vision"`, `title` kiểu "Đánh giá chất lượng ảnh",
"Trích xuất hình thái tổn thương".

### 4.4 Contract đầu ra

```python
class LesionMorphology(BaseModel):
    site: str
    color: list[str]
    shape: str
    border: str
    texture: str
    distribution: str
    size_mm: float | None
    asymmetry: bool | None

class VisionReport(BaseModel):
    usable: bool
    quality_issues: list[str]
    lesion_count: int
    lesions: list[LesionMorphology]
    classifier_topk: list[dict]      # [{label, prob, source}] — evidence thô
    narrative: str
    evidence_ids: list[str]          # do collect gán
```

---

## 5. Clinical Attribute Agent

### 5.1 Vai trò

Biến **mô tả triệu chứng tiếng Việt** thành **thuộc tính lâm sàng có cấu trúc**, rút **đầu mối
phân biệt**, rồi **truy xuất guideline** làm bằng chứng. **RAG là evidence provider — không đoán
bệnh.**

### 5.2 Nguyên tắc hoạt động (system prompt — rút gọn)

```
Bạn xử lý phần MÔ TẢ của bệnh nhân (không xem ảnh).

Ràng buộc:
- Chuẩn hoá lời nói dân dã sang thuật ngữ y khoa, GIỮ nguyên span gốc để truy vết.
- Chỉ trích thuộc tính có trong mô tả — KHÔNG bịa onset/severity nếu bệnh nhân không nói.
- differential_clues là ĐẦU MỐI ("nocturnal pruritus + đường hầm + lây trong nhà"), KHÔNG phải
  chẩn đoán.
- retrieve_evidence: xây query từ thuộc tính có cấu trúc, KHÔNG từ câu thô. Trả về passage +
  citation, không kết luận.
```

### 5.3 Pipeline

| Bước | Nguồn dữ liệu vào | Xử lý | LLM / công cụ | Kết quả ra |
|---|---|---|---|---|
| **normalize_terminology** | D1 (mô tả thô), D3 (memory nếu có tiền sử liên quan) | "ngứa nhiều về đêm" → `pruritus{severity:high, temporal:nocturnal}`; giữ `raw_span` | `get_llm("clinical")` (lite) | `terms: [{concept, value, raw_span}]` |
| **extract_attributes** | D8: `terms`; D1; D3 | Trích: onset, duration, temporal_pattern, severity (0–3), body_sites, associated_symptoms, triggers, relieving_factors, prior_treatments, allergies | `clinical` | `ClinicalAttributes` |
| **differential_clues** | D8: `ClinicalAttributes` | Rút đặc điểm có giá trị phân biệt (kết hợp triệu chứng + phân bố + diễn tiến) | `clinical` | `clues: list[str]` |
| **retrieve_evidence** | D8: `ClinicalAttributes` + `clues` (+ `vision_evidence.narrative` nếu đã có) | Ghép thành query text → embed → `search_guidelines` (D4) → lấy passage + `citation_key` + `url` + `relevance` | embedding + Qdrant (không LLM) | `retrieved_guidelines: list[GuidelineEvidence]` |

Mỗi bước phát step `agent="clinical"`.

### 5.4 Contract đầu ra

```python
class ClinicalAttributes(BaseModel):
    chief_complaint: str
    onset: str | None
    duration: str | None
    temporal_pattern: str | None       # nocturnal / intermittent / progressive...
    severity: int | None               # 0..3
    body_sites: list[str]
    associated_symptoms: list[str]
    triggers: list[str]
    relieving_factors: list[str]
    prior_treatments: list[str]
    allergies: list[str]
    differential_clues: list[str]
    normalized_terms: list[dict]
    evidence_ids: list[str]

class GuidelineEvidence(BaseModel):
    citation_key: str
    title: str
    snippet: str
    url: str | None
    relevance: float
```

---

## 6. Knowledge Graph Agent (CRKG)

### 6.1 Vai trò

Suy luận trên **Clinical Reasoning Knowledge Graph** (D5): ánh xạ triệu chứng + hình thái vào
node → đi theo quan hệ có trọng số để ra **danh sách bệnh ứng viên có điểm** (`P_graph`) → sinh
**câu hỏi phân biệt** → tra **red flag / chống chỉ định** của top ứng viên.

### 6.2 Nguyên tắc hoạt động

```
Bạn suy luận CHỈ dựa trên đồ thị CRKG. Mọi ứng viên bệnh phải kèm danh sách cạnh đã khớp
(matched_edges) và evidence_level của các cạnh đó.

Ràng buộc:
- KHÔNG dùng kiến thức ngoài đồ thị. Nếu triệu chứng không map được node nào → báo unmapped.
- score phản ánh: số triệu chứng khớp × trọng số cạnh × độ đặc hiệu, có xét severityRule.
- ask_more chỉ sinh khi ≥ 2 ứng viên sát điểm nhau; lấy câu hỏi từ Disease ──askMore──▶ Question.
```

### 6.3 Pipeline

| Bước | Nguồn dữ liệu vào | Xử lý | Công cụ | Kết quả ra |
|---|---|---|---|---|
| **map_entities** | D8: `clinical_attributes` (symptom, body_site, duration, trigger, history) + `vision_evidence.lesions` (visual feature, site) | Ánh xạ từng thuộc tính vào node CRKG (Symptom / VisualFeature / BodyArea / Duration / Trigger / MedicalHistory). Fuzzy + embedding cho từ đồng nghĩa | Neo4j lookup + embedding | `matched_nodes: list[NodeRef]`, `unmapped: list[str]` |
| **traverse** | D8: `matched_nodes`; D5 (cạnh `typicalSymptom` / `commonLocation` / `hasRisk` / `hasVisualFeature`) | Từ node đã map, đi ngược về Disease theo các cạnh; gom tập ứng viên + cạnh đã khớp | Cypher / graph traversal | `candidates: [{disease, matched_edges[], raw_score}]` |
| **score** | D8: `candidates`; D5 (`weight`, `evidence_level` trên cạnh; `severityRule` của disease) | `P_graph(d)` = f(Σ trọng số cạnh khớp, độ đặc hiệu triệu chứng, khớp severityRule); chuẩn hoá [0,1] | rule | `graph_scores: dict[disease, float]` |
| **ask_more** | D8: `candidates` sát điểm; D5 (`Disease ──askMore──▶ Question`) | Lấy câu hỏi phân biệt để loại trừ ứng viên | graph lookup | `differential_questions: list[str]` |
| **check_graph_safety** | D8: top-k `candidates`; D5 (`redFlag`, `requiresReferral`, `contraindicatedTreatment`) | Gom red flag + ngưỡng chuyển bác sĩ + chống chỉ định của các ứng viên hàng đầu | graph lookup | `kg_red_flags`, `contraindications` |

Mỗi bước phát step `agent="kg"`.

### 6.4 Contract đầu ra

```python
class KGReasoningResult(BaseModel):
    candidates: list[dict]            # [{disease, score, matched_edges[], evidence_level}]
    unmapped_attributes: list[str]
    differential_questions: list[str]
    kg_red_flags: list[str]
    contraindications: list[str]
    evidence_ids: list[str]
```

### 6.5 Nguồn dữ liệu của chính CRKG (D5)

- **Seed schema**: chuyên gia định nghĩa entity types + relation types + ràng buộc.
- **Làm giàu**: `scripts/build_crkg.py` — LLM đọc guideline (D4) đề xuất node/edge cho từng
  bệnh → **chuyên gia da liễu duyệt** (human-in-the-loop) → merge.
- **Metadata mỗi cạnh**: `relation`, `confidence` (0–1), `evidence_level` (guideline / expert /
  study), `condition`, `source`, `last_reviewed`.

---

## 7. Patient History Agent

### 7.1 Vai trò

Khai thác **hồ sơ bệnh án điện tử** (D7) để điều chỉnh nghi ngờ bệnh theo tiền sử, kết quả xét
nghiệm và đáp ứng điều trị trước đó. Chỉ chạy khi user đã đăng nhập và Orchestrator yêu cầu.

### 7.2 Nguyên tắc hoạt động

```
Bạn đọc hồ sơ bệnh án (CHỈ ĐỌC) và rút ra điều chỉnh cho suy luận chẩn đoán.

Ràng buộc:
- Chỉ truy cập hồ sơ của đúng user_id trong turn.
- history_adjustments là ĐIỀU CHỈNH điểm (tăng/giảm), không phải chẩn đoán mới.
- Nêu rõ căn cứ: "KOH(+) 2 tháng trước → giảm nghi eczema, tăng nghi nấm".
- Không log nội dung nhạy cảm ra trace SSE — chỉ tóm tắt điều chỉnh.
```

### 7.3 Pipeline

| Bước | Nguồn dữ liệu vào | Xử lý | Công cụ | Kết quả ra |
|---|---|---|---|---|
| **fetch_emr** | D7 (REST Core): `GET /internal/patients/{user_id}/derm-history` | Lấy chẩn đoán trước, lab results (KOH / biopsy / Wood's lamp / patch test), thuốc đang dùng, phác đồ + đáp ứng, dị ứng, bệnh nền, tiền sử gia đình | HTTP | `emr_snapshot` |
| **reason_history** | D8: `emr_snapshot` + `candidate_diagnoses` hiện tại (nếu vòng ≥ 2) | Áp luật: `KOH(+) → +nấm / −eczema`; `biopsy atypical → +malignancy`; `retinoid không đáp ứng → −ứng viên đáp ứng retinoid`; `tiểu đường → cảnh báo corticosteroid kéo dài`; `thai kỳ → chống chỉ định retinoid` | `get_llm("clinical")` + rule | `history_adjustments`, `contraindication_notes` |

Mỗi bước phát step `agent="history"`.

### 7.4 Contract đầu ra

```python
class HistoryEvidence(BaseModel):
    has_emr: bool
    prior_diagnoses: list[str]
    lab_results: list[dict]           # [{test, result, date}]
    treatment_responses: list[dict]   # [{treatment, response}]  response ∈ improved/noChange/worsened
    history_adjustments: dict         # disease -> delta điểm (dùng cho P_history)
    contraindication_notes: list[str]
    evidence_ids: list[str]
```

---

## 8. Safety Agent (Red-flag / Escalation)

### 8.1 Vai trò

**Không phải subgraph LLM tự do.** Là bộ **rule + tra CRKG** chạy trong `reflect` của
Orchestrator (và chạy sớm ngay sau `collect` nếu ảnh/triệu chứng gợi ý nguy hiểm). Trả về danh
sách cờ nguy hiểm; nếu có cờ mức cao → ép `aggregate` mở đầu bằng khuyến cáo đi khám ngay.

### 8.2 Bộ kiểm tra (nguồn dữ liệu → luật)

| Kiểm tra | Nguồn | Điều kiện kích hoạt |
|---|---|---|
| **Melanoma ABCDE** | `vision_evidence.lesions` (D2→D6) | asymmetry + border bất thường + ≥ 2 màu + size > 6mm + (diễn tiến từ D1) |
| **Nhiễm trùng lan nhanh** | `clinical_attributes` (D1) | sưng/đau tăng nhanh + sốt + chảy mủ + viền lan theo giờ |
| **SJS/TEN nghi ngờ** | `clinical_attributes`, `vision_evidence` | tổn thương niêm mạc + bong da diện rộng + đau + sau dùng thuốc mới |
| **Vị trí nguy hiểm** | `vision_evidence.lesions[].site` | quanh mắt / niêm mạc / sinh dục |
| **Triệu chứng toàn thân / phản vệ** | `clinical_attributes.associated_symptoms` (D1) | khó thở + phù mặt + mày đay lan toả |
| **Red flag theo bệnh** | D5: `Disease ──redFlag──▶ RedFlag`, `──requiresReferral──▶ ReferralRule` | với mỗi top ứng viên trong `candidate_diagnoses` |

### 8.3 Contract đầu ra

```python
class RedFlag(BaseModel):
    code: str                 # melanoma_abcde / rapid_infection / sjs_ten / mucosal / anaphylaxis / kg_referral
    severity: Literal["high", "moderate"]
    rationale: str
    evidence_ids: list[str]
    recommended_action: str   # "đi khám chuyên khoa trong 24h" / "cấp cứu ngay" ...
```

---

## 9. Tracing & nhãn agent trên SSE

- Mỗi node (Orchestrator + specialist) gọi `get_stream_writer()` → publish
  `reasoning.step_started → step_delta* → step_completed` lên Redis `agent:events:{cid}` →
  Core forward nguyên văn ra SSE.
- **Thay đổi hợp đồng duy nhất (additive, optional):** thêm field `agent: str | None` vào
  `ReasoningResult` + `ReasoningStepDto` + payload writer. `None` = graph chat cũ.
- FE gộp step theo `agent` (accordion + badge màu): `orchestrator` / `vision` / `clinical` /
  `kg` / `history`.
- Persist: `orchestrator_graph` kết thúc → `state["reasoning_trace"]` →
  `_persist_assistant(content=final_assessment, reasoning=trace)` +
  `extra.sources = retrieved_guidelines` → payload `message.done`.

---

## 10. Ví dụ luồng dữ liệu một ca

```
User: "da tay em nổi mảng đỏ, ngứa nhiều về đêm, 3 tuần chưa khỏi" + [ảnh mu bàn tay]
                                    │
understand_case  ◀── D1 + đếm D2(1 ảnh) + D3
   → case_summary: "tổn thương khu trú mu tay, ngứa mạn tính, có ảnh"
   → gaps: ["chưa rõ có vảy không", "chưa rõ tiếp xúc hoá chất", "chưa rõ lây trong nhà"]
                                    │
plan  → task_plan: [Vision(ảnh), Clinical(mô tả), KnowledgeGraph, History(user đã login)]
                                    │
dispatch ─┬─▶ VISION:   D2 → quality(usable) → lesion(mu tay, 1 mảng) →
          │             morphology(đỏ, ranh giới không rõ, có vảy mịn, ~2cm) →
          │             classifier: [{eczema 0.55},{psoriasis 0.20},{tinea 0.15}]
          │
          ├─▶ CLINICAL: D1 → normalize(pruritus nocturnal, plaque, 3w) →
          │             extract(onset 3w, severity 2, site=hand_dorsum) →
          │             clues["ngứa đêm + mạn tính + khu trú"] →
          │             retrieve_evidence: D4 → [AAD eczema hand 2024 #3, DermNet tinea manuum]
          │
          ├─▶ KG:       D8(clinical+vision) → map_entities → traverse D5 →
          │             candidates: [{eczema 0.6},{contact_dermatitis 0.5},{tinea 0.35}]
          │             ask_more: ["Có tiếp xúc chất tẩy rửa/hoá chất không?"]
          │             kg_red_flags: []
          │
          └─▶ HISTORY:  D7 → fetch_emr → KOH(+) cách đây 2 tháng, đã trị steroid không đỡ
                        reason_history → history_adjustments: {tinea:+0.3, eczema:-0.25}
                                    │
collect  → gán evidence_id: vis:lesion1, vis:cls, cln:attr, gl:aad_eczema#3, kg:cand:*, emr:koh
                                    │
reconcile → Fusion:
   Score(tinea)   = 0.4·0.15 + 0.3·0.35 + 0.2·0.6 + 0.1·0.8  ≈ 0.365
   Score(eczema)  = 0.4·0.55 + 0.3·0.60 + 0.2·0.5 + 0.1·0.25 ≈ 0.425  ← nhưng history mạnh chống
   conflicts: [classifier nghiêng eczema ↔ KOH(+) + không đáp ứng steroid nghiêng nấm]
   outcome: need_more (chưa hỏi tiếp xúc hoá chất) → HOẶC ask_user
                                    │
(ask_user) "Gần đây tay bạn có tiếp xúc hoá chất/chất tẩy rửa mới không?"  → "Không"
                                    │
reconcile (round 2) → loại bớt contact_dermatitis; nâng nghi tinea manuum do KOH(+) + steroid thất bại
                                    │
reflect (3R + Safety) → không red flag; confidence: tinea 0.55 / eczema 0.30 / khác 0.15
                                    │
aggregate →
  "Khả năng cao nhất: nấm da tay (tinea manuum) — do tiền sử soi tươi KOH dương tính và
   không đáp ứng corticosteroid, dù hình ảnh ban đầu giống chàm. Chẩn đoán phân biệt: chàm
   tiếp xúc/cơ địa. Nên: soi tươi KOH lại, tránh bôi corticosteroid đơn thuần. Nguồn: [AAD…],
   [DermNet…]. Đây là tư vấn sơ bộ, bạn nên khám da liễu để soi tươi xác định."
  sources: [gl:aad_eczema#3, gl:dermnet_tinea_manuum]
```
