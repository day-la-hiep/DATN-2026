# data-ingest

Xử lý dữ liệu thô -> dữ liệu sạch cho `core/`, **tổ chức theo nguồn**. Mỗi nguồn có cùng bố cục (và một `README.md` riêng mô tả nguồn, script, output):

```
<nguồn>/
├── input/     dữ liệu gốc (không commit — xem core/.gitignore)
├── scripts/   NN_*.py chạy lần lượt: input -> output
└── output/    kết quả của nguồn đó
```

| Nguồn | Input | Scripts | Output |
|---|---|---|---|
| `byt` | PDF BYT 75/QĐ-BYT 2015 | — (biên soạn tay) | `pdf_guideline_2015.json` — 65 bệnh |
| `who` | WHO fact sheets | — (biên soạn tay) | `who_skin_diseases.json` — 12 bệnh |
| `medlineplus` | MedlinePlus | — (biên soạn tay) | `medlineplus_skin_conditions.json` — 10 bệnh |
| `dermnet` | `skin_info.html` + `byt/output` | 01–05: lập chỉ mục topic, ánh xạ BYT↔topic, cào bài, dựng `post/{bệnh}/` | `dermnet_topics.*`, `dermnet_disease_related_topics.*`, `scraped_topics/`, `post/` |
| `dermo` | `dermatology.obo` | 01: parse ontology | `dermo_kg.json`, `dermo_terms.csv`, `dermo_term_map.json` |
| `primekg` | `kg.csv` (PrimeKG gốc) + `byt/output` | 01: lọc subgraph da liễu | `derma_nodes.csv` (5,2k), `derma_edges.csv` (19,7k) |
| **`01_normalize`** | `output/` của mọi nguồn trên | 01 bệnh · 02 KG · 03 manifest · `load_*.py` nạp Qdrant/Neo4j | `diseases/`, `kg/`, `manifest.json` |

## `01_normalize/` — điểm ra duy nhất cho `core/`

`core/` **chỉ đọc `01_normalize/output/`**, không đọc trực tiếp output của từng nguồn:

| Output | Ai dùng |
|---|---|
| `diseases/*.json` (87 bệnh, schema thống nhất, id duy nhất giữa các nguồn) | `load_knowledge_base.py`: chunk -> embed -> **Qdrant** (không qua file JSON) |
| `kg/primekg/` | `load_primekg.py` (Neo4j) |
| `kg/dermo/` | `load_dermo.py` (Neo4j) |
| `manifest.json` | số bản ghi + sha256 mỗi file, để biết bộ data đang deploy build từ đâu |

Thêm nguồn mới: tạo `<nguồn>/{input,scripts,output}`, (`run.py` tự nhận thư mục có `scripts/` hoặc `output/`), rồi cho
`01_normalize/scripts/` đọc output của nó.

## Chạy

```bash
cd core/data-ingest
python run.py --list                   # nguồn + script
python run.py normalize                # chuẩn hoá lại từ output có sẵn (nhanh, dùng nhiều nhất)
python run.py dermo primekg normalize  # chạy lại từ input cho các nguồn chỉ định
python run.py all                      # tất cả (dermnet bước 03 cào web — lâu)
```

Chỉ dùng thư viện chuẩn Python. `run.py` dừng ở script đầu tiên lỗi.

## Sau khi chạy

`run.py` chỉ tạo dữ liệu sạch. Nạp vào DB là bước riêng (cần Qdrant/Neo4j đang chạy và `core/.env`):

```bash
cd core
python data-ingest/01_normalize/scripts/load_knowledge_base.py [--reset]  # chunk + embed -> Qdrant
python data-ingest/01_normalize/scripts/load_primekg.py [--reset]         # Neo4j
python data-ingest/01_normalize/scripts/load_dermo.py [--reset]           # Neo4j
# prod: ../reset-and-gen-data.sh chạy cả 3 trong container
```

## Lưu ý

- `primekg` đã sửa lỗi lọc cạnh không xét `type` nút (id PrimeKG trùng số giữa các loại) — bộ cũ 474k cạnh
  chứa nhiều cạnh gen–gen/giải phẫu không liên quan. Neo4j cần nạp lại: `load_primekg.py --reset`.
- Docker: image chỉ cần `01_normalize/output/`; `core/Dockerfile.dockerignore` loại phần còn lại
  (input ~850MB, dermnet, output từng nguồn) khỏi build context.
