# byt — Bộ Y tế 75/QĐ-BYT (2015)

*Hướng dẫn chẩn đoán và điều trị các bệnh da liễu* (Bộ Y tế Việt Nam, ban hành 13/01/2015, 330 trang).
Nguồn gốc (neo) của toàn bộ hệ thống: 65 bệnh này là danh sách mà `primekg` và `dermnet` dùng để đối chiếu.

| | |
|---|---|
| Input | PDF gốc (không nằm trong repo) |
| Scripts | không có — dữ liệu được biên soạn/rà tay từ PDF |
| Output | `output/pdf_guideline_2015.json` — 65 bệnh |

## Schema (chung cho `byt`, `who`, `medlineplus`)

`id`, `name` (vi), `english_name`, `type`, `summary`, `common_features` (mã triệu chứng), `suggestive_phrases`,
`typical_locations`, `course`, `risk_factors`, `differential_diagnoses` (id bệnh khác) +
`differential_diagnosis_details`, `red_flags`, `safe_advice`, `references` (`source_id`, `page_start`, …),
`medical_review_status`.

Toàn bộ 65 bệnh đang ở `needs_clinical_review` — **chưa có bác sĩ duyệt**, không dùng như tư vấn y khoa.
`references[].source_id` = `byt_75_2015` (khai báo trong `core/knowledge_base/knowledge_base/sources.json`).

## Ai dùng

`01_normalize_diseases.py` kiểm tra -> `01_normalize/output/diseases/` -> chunking -> Qdrant. `primekg/01` và
`dermnet/02, 04` đọc thẳng file này làm danh sách bệnh mốc.
