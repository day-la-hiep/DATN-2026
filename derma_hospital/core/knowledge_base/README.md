# Xử Lý Dữ Liệu Guideline + Code Retrieval

> **Mục tiêu:** Các chiến thuật liên quan đến semantic retrieval, phân chia tài liệu
> **Output:** Vector DB + Tool Search

---

## Tổng Quan Pipeline

```
knowledge_base/diseases/*.json          ← Dữ liệu guideline gốc (BYT, WHO, MedlinePlus)
        │
        │  scripts/build_chunks_kb2.py
        ▼
Phân chia tài liệu → 87 bệnh × 5 chunks = 435 chunks
        │
        │  scripts/build_index_from_chunks.py
        ▼
Vector DB (FAISS) — 435 vectors × 384 chiều
        │
        ├── src/semantic.py     → Semantic Retrieval (search theo nghĩa)
        └── src/tools.py        → Tool Search (LLM tự gọi khi cần)
             └── src/medical_rag.py → Vòng lặp Tool Call ↔ LLM
```

---

## Dữ Liệu Guideline

| File | Nguồn | Số bệnh |
|---|---|---|
| `knowledge_base/diseases/pdf_guideline_2015.json` | BYT 75/QĐ-BYT 2015 | 65 |
| `knowledge_base/diseases/who_skin_diseases.json` | WHO Fact Sheets | 12 |
| `knowledge_base/diseases/medlineplus_skin_conditions.json` | MedlinePlus | 10 |
| **Tổng** | | **87 bệnh** |

---

## Công Việc 1 — Phân Chia Tài Liệu (Chunking)

**File:** `scripts/build_chunks_kb2.py`

Mỗi bệnh được chia thành **tối đa 5 chunk** theo ngữ nghĩa:

| Chunk Type | Nội dung | Trường JSON nguồn |
|---|---|---|
| `overview` | Tên, tóm tắt, phân loại, diễn tiến | `name`, `summary`, `type`, `course` |
| `symptoms` | Triệu chứng, vị trí, cụm từ đặc trưng | `common_features`, `typical_locations`, `suggestive_phrases` |
| `differential` | Phân biệt chẩn đoán | `differential_diagnosis_details`, `differential_diagnoses` |
| `advice` | Lời khuyên chăm sóc | `safe_advice` |
| `risk` | Yếu tố nguy cơ, dấu hiệu cảnh báo | `risk_factors`, `red_flags` |

**Mỗi chunk chứa:**
- `chunk_id` — định danh duy nhất `"benh_ghe::symptoms"`
- `chunk_type` — loại chunk để filter khi search
- `text` — văn bản sẽ được embed → vector
- `source_label` / `source_page` — trích dẫn nguồn y tế
- `disease` — toàn bộ object bệnh (dùng khi render response)

**Chạy:**
```bash
python scripts/build_chunks_kb2.py
# Output: data/chunks/all_chunks.json (435 chunks)
```

---

## Công Việc 2 — Vector DB (FAISS)

**Files:** `scripts/build_index_from_chunks.py` + `src/semantic.py`

### Build Index

- **Embedding model:** `paraphrase-multilingual-MiniLM-L12-v2` — hỗ trợ tiếng Việt, vector 384 chiều
- **FAISS Index:** `IndexFlatIP` — Inner Product (= cosine khi đã normalize)
- Tìm top-K trong < 1 millisecond với 435 vectors

```bash
python scripts/build_index_from_chunks.py
# Output:
#   data/semantic_index/conditions.faiss  (652 KB)
#   data/semantic_index/chunks.json       (1.4 MB)
```

### Search

```python
retriever = SemanticRetriever("data/semantic_index")
matches = retriever.search(
    message="bị ngứa về đêm ở kẽ ngón tay",
    limit=3,
    chunk_type="symptoms"   # filter theo loại chunk
)
# → benh_ghe::symptoms (0.465), benh_ghe_who::symptoms (0.459)
```

---

## Công Việc 3 — Tool Search

**Files:** `src/tools.py` + `src/medical_rag.py`

LLM nhận schema `search_disease_guidelines` và **tự quyết định** khi nào gọi, với `chunk_type` nào:

```
User hỏi về triệu chứng  → LLM gọi tool với chunk_type="symptoms"
User hỏi phân biệt bệnh  → LLM gọi tool với chunk_type="differential"
User hỏi cách chăm sóc   → LLM gọi tool với chunk_type="advice"
```

Vòng lặp Tool Call (tối đa 3 vòng):
```
LLM → gọi tool → FAISS search → kết quả → LLM tổng hợp → Response
```

---

## Chạy Pipeline

```bash
# Bước 1: Tạo chunks
python scripts/build_chunks_kb2.py

# Bước 2: Build Vector DB
python scripts/build_index_from_chunks.py

# Bước 3 (tuỳ chọn): Cấu hình LLM cho Tool Search
export OPENAI_API_KEY=sk-...
```

---

## Cấu Trúc

```
knowledge_base/
├── README.md                        ← File này
├── scripts/
│   ├── build_chunks_kb2.py          ← Phân chia tài liệu
│   └── build_index_from_chunks.py   ← Build Vector DB
├── src/
│   ├── semantic.py                  ← Semantic Retrieval
│   ├── tools.py                     ← Tool Search
│   └── medical_rag.py               ← LLM Tool Call loop
└── knowledge_base/
    ├── diseases/                    ← 87 bệnh da liễu (BYT + WHO + MedlinePlus)
    ├── safety/
    └── symptoms/
```