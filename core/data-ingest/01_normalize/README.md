# 01_normalize — chuẩn hóa, gom mọi nguồn và nạp vào database

Điểm ra **duy nhất** của `data-ingest`: `core/` chỉ đọc `01_normalize/output/`, và các script nạp DB nằm ở đây.

| | |
|---|---|
| Input | `output/` của `byt`, `who`, `medlineplus`, `primekg`, `dermo` |
| Output | `output/diseases/`, `output/kg/`, `output/manifest.json` |

## Bước 1 — chuẩn hóa (tự động, `python ../run.py normalize`, ~1 giây, chỉ thư viện chuẩn)

| Script | Việc |
|---|---|
| `01_normalize_diseases.py [-v]` | Gom 3 nguồn guideline (87 bệnh): kiểm tra field bắt buộc/kiểu dữ liệu, strip + khử trùng lặp trong các field list, **id duy nhất giữa các nguồn** (lỗi -> dừng). Cảnh báo (không dừng) khi `differential_diagnoses` trỏ tới id chưa có bài riêng (hiện 73, phần lớn BYT nhắc bệnh không nằm trong 65 bài). Giữ nguyên tên file gốc vì tên file được dùng làm `source_file` của chunk. |
| `02_normalize_kg.py` | Kiểm tra CSV PrimeKG đúng header, không có cạnh trỏ tới nút không tồn tại; `dermo_kg.json` có `terms` và id duy nhất; rồi chép vào `output/kg/`. |
| `03_build_manifest.py` | Ghi `manifest.json`: kích thước, số bản ghi, sha256 từng file + thời điểm tạo. |

Hiện `01` chỉ **kiểm tra**, chưa biến đổi nội dung: dữ liệu ba nguồn đã sạch nên output trùng input.

## Bước 2 — nạp vào database (chạy tay, cần DB đang chạy + `core/.env`)

Không đánh số nên `run.py` không tự chạy. Chạy từ `core/` (trong container prod: `../reset-and-gen-data.sh`).

| Script | Đọc | Ghi vào |
|---|---|---|
| `load_knowledge_base.py` | `output/diseases/*.json` | **Qdrant** `derma_kb_chunks`: chia mỗi bệnh tối đa 5 chunk (overview, symptoms, differential, advice, risk) -> embed local -> upsert **thẳng**, không tạo file JSON. Idempotent, chạy lại thì bỏ qua chunk đã có. |
| `load_primekg.py` | `output/kg/primekg/*.csv` | **Neo4j** `:Entity` + label theo loại, cạnh theo `relation` |
| `load_dermo.py` | `output/kg/dermo/dermo_kg.json` | **Neo4j** `:DermoTerm`, cạnh `IS_A` và quan hệ OBO |

Cả 3 nhận `--reset` (xóa dữ liệu cũ trước khi nạp). `load_knowledge_base.py` còn có `--dry-run`
(chỉ chunk + báo cáo, không cần Qdrant) và `--dump-chunks FILE` (ghi thêm chunk ra JSON để debug).

`manifest.json` để đối chiếu bộ data đang deploy (phát hiện file bị sửa tay).
Thư mục này được commit và đưa vào Docker image cùng `scripts/` của nó (các nguồn khác bị loại — xem `core/Dockerfile.dockerignore`).
