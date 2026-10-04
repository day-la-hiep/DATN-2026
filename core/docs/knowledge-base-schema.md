# Schema Knowledge Base — Derma

Tài liệu mô tả **schema hiện tại** (2026-09-28, nhánh `ingest/fritzpatrick-data`) của knowledge base mà agent dùng.
Nguồn sự thật là code trong `core/data_ingest/01_normalize/scripts/` và `core/app/infra/qdrant_client.py` — doc này
chỉ tổng hợp lại, nếu lệch thì code đúng.

## 1. Tổng quan

```
 Nguồn thô (data_ingest/<nguồn>/)          Chuẩn hoá (01_normalize/output/)        Lưu trữ runtime
 ─────────────────────────────────         ────────────────────────────────        ─────────────────────────────
 byt (65) ┐                                                                        Qdrant
 who (12) ├─> 01_normalize_diseases ─> diseases/*.json (87 bệnh) ─┬─ load_knowledge_base ─> derma_kb_chunks (435)
 medlineplus (10) ┘          04_link_dermo_ids (gắn dermo_id) ────┘
 primekg (kg.csv) ─> 02_normalize_kg ─> kg/primekg/*.csv ─────────── load_primekg ─> Neo4j :Entity (PrimeKG)
 dermo (.obo)     ─> 02_normalize_kg ─> kg/dermo/dermo_kg.json ───── load_dermo ───> Neo4j :DermoTerm
                                             Neo4j phenotype ─────── load_phenotypes ─> derma_phenotypes
 fritpatrick_color_atlas ─> pages.jsonl, sections_index.json   (CHƯA gom vào 01_normalize, core chưa đọc)
```

| Kho | Tên | Nội dung | Số lượng | Script nạp |
|---|---|---|---|---|
| Qdrant | `derma_kb_chunks` | Chunk guideline bệnh (vector) | 87 bệnh → 435 chunk | `load_knowledge_base.py` |
| Qdrant | `derma_phenotypes` | Phenotype PrimeKG có nối bệnh (vector) | phụ thuộc Neo4j | `load_phenotypes.py` |
| Neo4j | `:Entity` + label loại | Subgraph da liễu PrimeKG | 5 159 node · 19 708 cạnh | `load_primekg.py` |
| Neo4j | `:DermoTerm` | Ontology DermO | 3 427 term (26 obsolete) | `load_dermo.py` |
| Qdrant | `agent_memories` | Long-term memory user (hạ tầng cũ, không dùng) | — | — |

Embedding: local `sentence-transformers` **`paraphrase-multilingual-MiniLM-L12-v2`, dim 384**, cosine, vector đã
normalize (`core/agent/embeddings.py`). Đổi model ⇒ phải `--reset` cả 2 collection Qdrant.

Thứ tự nạp: `load_primekg` → `load_dermo` → `load_phenotypes` (đọc Neo4j) ; `04_link_dermo_ids` → `load_knowledge_base`.

---

## 2. Bệnh đã chuẩn hoá — `01_normalize/output/diseases/*.json`

Mỗi file là một mảng object bệnh; tên file được giữ nguyên và dùng làm `source_file`.

| File | Nguồn | Số bệnh |
|---|---|---|
| `pdf_guideline_2015.json` | BYT 75/QĐ-BYT 2015 | 65 |
| `who_skin_diseases.json` | WHO fact sheets | 12 |
| `medlineplus_skin_conditions.json` | MedlinePlus | 10 |

### Schema một bệnh

| Field | Kiểu | Bắt buộc | Ghi chú |
|---|---|---|---|
| `id` | str | ✔ | slug không dấu, **duy nhất giữa mọi nguồn** (vd `benh_choc`) |
| `name` | str | ✔ | tên tiếng Việt |
| `english_name` | str | | dùng để match DermO |
| `type` | str | | nhóm bệnh (vd "Bệnh da nhiễm khuẩn") |
| `summary` | str | ✔ | tóm tắt |
| `course` | str | | diễn tiến |
| `common_features` | list[str] | | mã triệu chứng dạng slug (`mun_nuoc`, `vay_mat_ong`) |
| `suggestive_phrases` | list[str] | | cụm từ đặc trưng, văn tự nhiên |
| `typical_locations` | list[str] | | vị trí tổn thương |
| `risk_factors` | list[str] | | |
| `red_flags` | list[str] | | mã dạng slug (`sot_cao`, `lan_nhanh`) |
| `safe_advice` | list[str] | | lời khuyên an toàn, câu đầy đủ |
| `differential_diagnoses` | list[str] | | **id bệnh** cần phân biệt — có thể trỏ tới id không có bài riêng (hiện 73 id, chỉ cảnh báo) |
| `differential_diagnosis_details` | str | | văn bản phân biệt chẩn đoán |
| `references` | list[Reference] | | phần tử đầu tiên được dùng làm nguồn của chunk |
| `medical_review_status` | str | | vd `needs_clinical_review` |
| `dermo_id` | str \| null | | gắn bởi `04_link_dermo_ids.py` — **64/87** bệnh khớp |

`Reference`: `{source_id, title, publisher, page_start?, year?, url?}` — BYT có `page_start`/`year`, WHO/MedlinePlus có `url`.

Validate (`01_normalize_diseases.py`): đủ field bắt buộc, field list phải là list, strip + khử trùng lặp phần tử list,
id trùng ⇒ dừng.

`dermo_id` được match **chính xác** (lowercase) `english_name` (và các phần tách bởi `/`, `,`) rồi `name` với
`dermo/output/dermo_term_map.json` (5 470 tên/đồng nghĩa → id). Không dùng fuzzy match có chủ đích.

---

## 3. Qdrant `derma_kb_chunks` — chunk guideline

Mỗi bệnh → tối đa 5 chunk (hiện đủ 5 cho cả 87 bệnh = 435 point).

| `chunk_type` | Text được embed ghép từ |
|---|---|
| `overview` | `name`, `english_name`, `type`, `summary`, `course` |
| `symptoms` | `common_features`, `typical_locations`, `suggestive_phrases` |
| `differential` | `differential_diagnoses`, `differential_diagnosis_details` |
| `advice` | `safe_advice` |
| `risk` | `risk_factors`, `red_flags` |

- **Point id**: `uuid5(NAMESPACE_URL, chunk_id)`, `chunk_id = "<disease_id>::<chunk_type>"` → nạp lại idempotent, bỏ qua chunk đã có.
- **Vector**: 384 chiều, cosine.

**Payload**

| Key | Kiểu | Ghi chú |
|---|---|---|
| `chunk_id` | str | `benh_choc::overview` |
| `chunk_type` | str | 1 trong 5 loại trên — dùng làm filter |
| `disease_id` | str | khoá nối về bệnh, filter trong `get_kb_chunks_by_disease_id` |
| `dermo_id` | str \| null | cầu nối sang DermO/PrimeKG, filter trong `get_kb_disease_id_by_dermo_id` |
| `disease_name` | str | |
| `english_name` | str | |
| `disease_type` | str | |
| `text` | str | văn bản đã embed |
| `source_label` | str | `"BYT 75/QĐ-BYT 2015"` hoặc `source_id` thô |
| `source_page` | int \| null | trang tài liệu gốc (chỉ BYT) |
| `source_file` | str | tên file JSON nguồn |

> Chunk trong bộ nhớ còn có `source_doc`, `medical_review_status`, `disease` (object đầy đủ) nhưng **không** được ghi
> vào payload Qdrant (chỉ xuất hiện khi `--dump-chunks`).

Truy cập: `search_disease_guidelines` (semantic, filter `chunk_type`), `get_disease_guideline_profile` (theo `disease_id`),
`find_disease_id_by_dermo_id` (không phải tool).

---

## 4. Neo4j — PrimeKG (`:Entity`)

Nguồn: `kg/primekg/derma_nodes.csv` (`id,name,type,source`) và `derma_edges.csv`
(`relation,display_relation,x_id,x_name,x_type,y_id,y_name,y_type`).

### Node

Mỗi node có 2 label: `:Entity` + label theo `type` (PascalCase). Constraint `entity_id`: `Entity.id` UNIQUE.

| `type` | Label | `source` | Số node |
|---|---|---|---|
| `gene/protein` | `:GeneProtein` | NCBI | 2 364 |
| `disease` | `:Disease` | MONDO / MONDO_grouped | 1 335 |
| `effect/phenotype` | `:EffectPhenotype` | HPO | 951 |
| `drug` | `:Drug` | DrugBank | 509 |

Thuộc tính: `id` (str, số thuần của PrimeKG), `name`, `type`, `source`.

### Quan hệ

Relationship type = `relation` viết hoa, thuộc tính `display_relation`. PrimeKG lưu **cả 2 chiều** nên mỗi quan hệ có
2 cạnh có hướng ngược nhau.

| Relationship type | `display_relation` | Giữa | Số cạnh (tổng 2 chiều) |
|---|---|---|---|
| `DISEASE_PROTEIN` | associated with | Disease ↔ GeneProtein | 8 166 |
| `DISEASE_DISEASE` | parent-child | Disease ↔ Disease | 3 132 |
| `DISEASE_PHENOTYPE_POSITIVE` | phenotype present | Disease ↔ EffectPhenotype | 5 088 |
| `DISEASE_PHENOTYPE_NEGATIVE` | phenotype absent | Disease ↔ EffectPhenotype | 90 |
| `INDICATION` | indication | Drug ↔ Disease | 1 734 |
| `CONTRAINDICATION` | contraindication | Drug ↔ Disease | 1 146 |
| `OFF_LABEL_USE` | off-label use | Drug ↔ Disease | 352 |

Truy cập: `query_dermatology_kg` (text→Cypher, tự introspect schema), `ground_medical_entities`,
`expand_entity_context`, `generate_differential`.

---

## 5. Neo4j — DermO ontology (`:DermoTerm`)

Tách riêng khỏi `:Entity` (namespace id khác: `DERMO:0000000` vs số). Constraint `dermo_term_id`: `DermoTerm.id` UNIQUE.

| Thuộc tính | Kiểu |
|---|---|
| `id` | str (`DERMO:0002066`) |
| `name` | str |
| `def` | str |
| `synonyms` | list[str] |
| `xrefs` | list[str] (SNOMEDCT, DOID, …) |
| `alt_ids` | list[str] |
| `is_obsolete` | bool |

| Relationship | Chiều | Số cạnh |
|---|---|---|
| `IS_A` | con → cha | 3 817 |
| `HAS_SYMPTOM` | term → term | 126 |
| `RESULTS_IN` | term → term | 30 |
| `ASSOCIATED_WITH` | term → term | 18 |
| `DERIVES_FROM` | term → term | 2 |

Gốc cây: `DERMO:0000000 disease` → `DERMO:0000001 cutaneous disease` → …

Truy cập: `lookup_dermo_term`, `ground_medical_entities`, `expand_entity_context`.

---

## 6. Qdrant `derma_phenotypes`

Nạp từ Neo4j: các node `:Entity {type:'effect/phenotype'}` có ≥1 cạnh `DISEASE_PHENOTYPE_POSITIVE|NEGATIVE`.

- **Point id**: `uuid5(NAMESPACE_URL, "primekg-phenotype:<id>")`
- **Text embed**: `name` + `". "` + các synonym DermO (nếu tên khớp chính xác một `:DermoTerm` không obsolete)
- **Payload**: `{primekg_id, name, synonyms}` — `primekg_id` khớp `Entity.id`

Truy cập: `describe_morphology` (mô tả tự do → phenotype).

---

## 7. Cầu nối giữa các kho

```
Qdrant derma_kb_chunks.dermo_id ──(==)──> Neo4j :DermoTerm.id
Qdrant derma_phenotypes.primekg_id ─(==)─> Neo4j :Entity.id
Neo4j :DermoTerm  <── không có cạnh ──>  Neo4j :Entity   (chỉ nối bằng so khớp tên/synonym lúc query)
```

- Khoá cứng duy nhất KB ↔ ontology là `dermo_id` (64/87 bệnh). 23 bệnh còn lại chỉ tra được bằng semantic search.
- PrimeKG ↔ DermO **không** có id chung; tool nối bằng tên/synonym tại runtime.

---

## 8. Nguồn đang xây dựng — Fitzpatrick's Color Atlas (8th ed.)

`data_ingest/fritpatrick_color_atlas/` — **chưa** được `01_normalize` gom và chưa nạp vào kho nào.
Nội dung có bản quyền McGraw-Hill, chỉ dùng nội bộ.

| File | Schema |
|---|---|
| `output/pages.jsonl` | mỗi dòng `{page: int, text: str}` — 968 trang, text OCR (nhiễu) |
| `output/sections_index.json` | mảng ~850 heading `{name, name_norm, icd10, page_start, line, page_end, end_line, minor}` |
| `selected/<slug>.{json,md}` | do `select_diseases.py` sinh ra (chạy tay) |

`minor = true` là heading phụ (Management/Diagnosis/Staging…) thuộc bệnh chính đứng trước. `icd10` đã sửa lỗi OCR
(`835` → `B35`). Với `--from-byt` hiện 18/65 bệnh BYT chưa khớp heading nào.

---

## 9. Vấn đề đã biết

1. **PrimeKG: 1 286 / 19 708 cạnh (~6,5%) nối sai loại node.** `derma_nodes.csv` chỉ có một dòng cho mỗi `id`, nhưng
   id PrimeKG trùng số giữa các loại (vd id `972` vừa là phenotype *Palmoplantar hyperkeratosis* vừa là gene *CD74*).
   Loader `MATCH (:Entity {id})` nên cạnh `DISEASE_PHENOTYPE_*` có thể trỏ nhầm sang gene/disease. 200 phenotype được
   cạnh tham chiếu không có node phenotype tương ứng. `02_normalize_kg.py` chỉ kiểm tra id tồn tại, không kiểm tra
   `type`. Hướng sửa: khoá node theo `(type, id)` (vd id ghép `"<type>:<id>"`) ở `primekg/scripts` + loader.
2. `01_normalize_diseases.py` đặt mặc định `differential_diagnosis_details = []` nhưng dữ liệu thực là `str` — kiểu
   không nhất quán nếu nguồn mới thiếu field này.
3. Comment `EMBEDDING_DIM = 768` trong `app/infra/qdrant_client.py` đã cũ (chỉ áp cho `agent_memories`); KB dùng 384.
4. README `01_normalize` chưa nhắc `04_link_dermo_ids.py` và `load_phenotypes.py`.
