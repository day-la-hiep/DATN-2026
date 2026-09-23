# primekg — PrimeKG (knowledge graph y sinh) lọc theo da liễu

Từ PrimeKG gốc (~8 triệu cạnh) chỉ giữ subgraph quanh các **bệnh da liễu**, neo vào 65 bệnh BYT
và các từ khóa ICD-10 chương XII (L00–L99).

| | |
|---|---|
| Input | `input/kg.csv` (PrimeKG gốc, ~850MB, không commit) + `../byt/output/pdf_guideline_2015.json` |
| Script | `scripts/01_extract_derma_subgraph.py [--output-dir DIR]` (~15 giây) |
| Output | `output/derma_nodes.csv`, `derma_edges.csv`, `entity_mapping.json`, `derma_kg.json` |

Chạy: `python ../run.py primekg`.

## Cách lọc

1. **Quét 1:** nút `disease` có tên trùng bệnh BYT (tiếng Anh) hoặc khớp từ khóa da liễu -> 599 nút bệnh mốc
   (42/65 bệnh BYT ánh xạ được -> `entity_mapping.json`).
2. **Quét 2:** giữ cạnh có 1 đầu là bệnh mốc, đầu kia là `disease` / `effect/phenotype` / `drug` / `gene/protein`.

Kết quả: 5.159 nút (gene 2.364 · disease 1.335 · phenotype 951 · drug 509), 19.708 cạnh, gồm đúng 7 loại quan hệ:
`disease_protein`, `disease_phenotype_positive/negative`, `disease_disease`, `indication`, `contraindication`, `off-label use`.

## Lưu ý

- Id PrimeKG chỉ duy nhất **trong từng loại nút** (id bệnh có thể trùng số với id gen). Script so cả `type`
  khi chọn cạnh; bản trước chỉ so id nên kéo vào ~64k cạnh gen–gen/giải phẫu không liên quan da liễu.
- Loader Neo4j (`core/data-ingest/01_normalize/scripts/load_primekg.py`) đặt `id` là unique trên `:Entity`; output hiện có 0 id trùng giữa các loại.
- `derma_kg.json` (bản JSON cùng subgraph) không ai đọc và bị `.gitignore`.
- Đổi output xong phải `run.py normalize` rồi nạp lại Neo4j: `python data-ingest/01_normalize/scripts/load_primekg.py --reset`.
