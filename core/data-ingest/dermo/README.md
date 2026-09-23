# dermo — DermO (Dermatology Ontology)

Ontology thuật ngữ da liễu (OBO 1.2): 3.427 term (26 obsolete), quan hệ `is_a` và `relationship`
(vd `has_symptom`). Dùng để chuẩn hóa thuật ngữ người dùng gõ về 1 khái niệm (tool `lookup_dermo_term`).

| | |
|---|---|
| Input | `input/dermatology.obo` (không commit) |
| Script | `scripts/01_process_dermo_ontology.py` — chỉ dùng thư viện chuẩn |
| Output | `output/dermo_kg.json`, `dermo_terms.csv`, `dermo_term_map.json` |

Chạy: `python ../run.py dermo`.

| Output | Nội dung |
|---|---|
| `dermo_kg.json` | `metadata` + `terms[]` (`id`, `name`, `def`, `synonyms`, `xrefs`, `is_a`, `relationships`, `alt_ids`, `is_obsolete`) — **đầu vào của `load_dermo.py` (Neo4j)** |
| `dermo_terms.csv` | bảng phẳng mỗi term, để xem/đối chiếu |
| `dermo_term_map.json` | "tên/synonym (lowercase) -> DERMO id" (5.470 mục), bỏ term obsolete |

Id term dạng `DERMO:0000001` — namespace khác PrimeKG nên Neo4j dùng label riêng `:DermoTerm`.
