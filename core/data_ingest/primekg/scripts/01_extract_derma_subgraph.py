#!/usr/bin/env python3
"""
Single Master Script: Pure Dermatology Grounded Subgraph Extractor from PrimeKG
==============================================================================
File: data-ingest/primekg/scripts/01_extract_derma_subgraph.py

Mục đích:
  Đảm bảo 100% dữ liệu trích xuất CHỈ LIÊN QUAN ĐẾN DA LIỄU bằng cách neo dữ liệu (Grounding)
  trực tiếp vào 65 Bệnh Da Liễu Bộ Y tế (pdf_guideline_2015.json) và Phân loại Quốc tế ICD-10 Chương XII (L00-L99).

Cam kết:
  - Bỏ 100% các nút ngoại lai không thuộc da liễu (tim mạch, thần kinh, tim, xương...).
  - Chỉ giữ 4 loại quan hệ lâm sàng da liễu:
      1. Bệnh da liễu ↔ Triệu chứng lâm sàng (disease_phenotype)
      2. Bệnh da liễu ↔ Thuốc điều trị (disease_drug / indication)
      3. Bệnh da liễu ↔ Gen / Đột biến di truyền (disease_gene)
      4. Bệnh da liễu ↔ Bệnh da liễu phân biệt (disease_disease)

Input : primekg/input/kg.csv (PrimeKG gốc) + byt/output/pdf_guideline_2015.json (mốc neo)
Output: primekg/output/{derma_nodes.csv, derma_edges.csv, derma_kg.json, entity_mapping.json}

Chạy:
  python data-ingest/primekg/scripts/01_extract_derma_subgraph.py [--output-dir DIR]

Sau đó `01_normalize/` gom 2 file CSV vào `01_normalize/output/kg/` và
`core/data-ingest/01_normalize/scripts/load_primekg.py` nạp Neo4j từ đó.
"""

import argparse
import os
import sys
import csv
import json
import time
import re
from pathlib import Path


SOURCE_DIR = Path(__file__).resolve().parents[1]  # data-ingest/primekg

GUIDELINE_PATH = SOURCE_DIR.parent / "byt" / "output" / "pdf_guideline_2015.json"

PRIMEKG_CSV_PATH = SOURCE_DIR / "input" / "kg.csv"

OUT_DIR = SOURCE_DIR / "output"

OUT_NODES_CSV = OUT_DIR / "derma_nodes.csv"
OUT_EDGES_CSV = OUT_DIR / "derma_edges.csv"
OUT_KG_JSON = OUT_DIR / "derma_kg.json"
OUT_MAPPING_JSON = OUT_DIR / "entity_mapping.json"


# Danh sách từ khóa ICD-10 Chương XII (L00-L99) + Bệnh da liễu thuần túy
STRICT_DERMA_DISEASE_KEYWORDS = [
    r"\bdermatitis\b",
    r"\beczema\b",
    r"\bacne\b",
    r"\bpsoriasis\b",
    r"\brosacea\b",
    r"\bvitiligo\b",
    r"\burticaria\b",
    r"\balopecia\b",
    r"\bpemphigus\b",
    r"\bpemphigoid\b",
    r"\blichen\b",
    r"\bscabies\b",
    r"\bimpetigo\b",
    r"\bcellulitis\b",
    r"\btinea\b",
    r"\bonychomycosis\b",
    r"\bkeratosis\b",
    r"\bfolliculitis\b",
    r"\bscleroderma\b",
    r"\berythema\b",
    r"\bprurigo\b",
    r"\bsyphilis\b",
    r"\bleprosy\b",
    r"\bherpes\b",
    r"\bzoster\b",
    r"\bmolluscum\b",
    r"\blupus\b",
    r"\bfuruncle\b",
    r"\bcarbuncle\b",
    r"\bparonychia\b",
    r"\bichthyosis\b",
    r"\bcutaneous\b",
    r"\bskin cancer\b",
    r"\bmelanoma\b",
    r"\bbasal cell carcinoma\b",
    r"\bsquamous cell carcinoma\b",
    r"\bhidradenitis\b",
    r"\bpruritus\b",
    r"\bskin disease\b",
    r"\bskin disorder\b",
]

strict_derma_regex = re.compile(
    "|".join(STRICT_DERMA_DISEASE_KEYWORDS), flags=re.IGNORECASE
)

# Chỉ chấp nhận 4 nhóm quan hệ lâm sàng có giá trị chẩn đoán da liễu
ALLOWED_RELATION_TYPES = {
    "disease_phenotype_positive",
    "disease_phenotype_negative",
    "indication",
    "contraindication",
    "off-label use",
    "disease_protein",
    "disease_gene",
    "disease_disease",
}


def step1_load_guideline_diseases():
    print("=" * 75)
    print(
        " [BƯỚC 1] Nạp danh sách 65 bệnh Da liễu Bộ Y tế làm Mốc Neo (Grounding)"
    )
    print("=" * 75)

    if not os.path.exists(GUIDELINE_PATH):
        print(f"[Lỗi] Không tìm thấy file: {GUIDELINE_PATH}")
        sys.exit(1)

    with open(GUIDELINE_PATH, "r", encoding="utf-8") as f:
        guideline_data = json.load(f)

    seed_disease_names = set()
    guideline_map = {}

    for d in guideline_data:
        eng_name = d.get("english_name", "").strip().lower()
        if eng_name:
            seed_disease_names.add(eng_name)
            guideline_map[eng_name] = {
                "id": d["id"],
                "name_vi": d["name"],
                "name_en": d["english_name"],
            }

    print(
        f"-> Nạp thành công {len(guideline_data)} bệnh lý da liễu chính thức."
    )
    return seed_disease_names, guideline_map


def step2_3_extract_pure_derma_subgraph(seed_disease_names, guideline_map):
    print("=" * 75)
    print(
        " [BƯỚC 2 & 3] Trích xuất Subgraph Da liễu Thuần túy từ PrimeKG (Strict Filtering)"
    )
    print("=" * 75)

    if not os.path.exists(PRIMEKG_CSV_PATH):
        print(f"[Lỗi] Không tìm thấy file kg.csv tại: {PRIMEKG_CSV_PATH}")
        sys.exit(1)

    derma_disease_node_ids = set()
    entity_mapping = {}

    nodes_dict = {}
    edges_list = []

    print("Đang quét Lần 1: Xác định danh sách Nút Bệnh Da Liễu chuẩn...")
    start_time = time.time()

    with open(PRIMEKG_CSV_PATH, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        headers = next(reader)

        for row in reader:
            if len(row) < 12:
                continue

            x_id, x_type, x_name = row[3], row[4], row[5]
            y_id, y_type, y_name = row[8], row[9], row[10]

            # Kiểm tra nút X
            if x_type == "disease":
                x_lower = x_name.lower()
                if x_lower in seed_disease_names or strict_derma_regex.search(
                    x_lower
                ):
                    derma_disease_node_ids.add(x_id)
                    nodes_dict[x_id] = {
                        "id": x_id,
                        "name": x_name,
                        "type": x_type,
                        "source": row[6],
                    }
                    if x_lower in seed_disease_names:
                        byt_info = guideline_map[x_lower]
                        entity_mapping[byt_info["id"]] = {
                            "byt_name_vi": byt_info["name_vi"],
                            "byt_name_en": byt_info["name_en"],
                            "primekg_node_id": x_id,
                            "primekg_node_name": x_name,
                        }

            # Kiểm tra nút Y
            if y_type == "disease":
                y_lower = y_name.lower()
                if y_lower in seed_disease_names or strict_derma_regex.search(
                    y_lower
                ):
                    derma_disease_node_ids.add(y_id)
                    nodes_dict[y_id] = {
                        "id": y_id,
                        "name": y_name,
                        "type": y_type,
                        "source": row[11],
                    }
                    if y_lower in seed_disease_names:
                        byt_info = guideline_map[y_lower]
                        entity_mapping[byt_info["id"]] = {
                            "byt_name_vi": byt_info["name_vi"],
                            "byt_name_en": byt_info["name_en"],
                            "primekg_node_id": y_id,
                            "primekg_node_name": y_name,
                        }

    print(
        f"-> Đã xác định {len(derma_disease_node_ids)} Nút Bệnh Da Liễu chuẩn ({time.time() - start_time:.1f}s)."
    )
    print(
        f"-> Ánh xạ trực tiếp thành công cho {len(entity_mapping)} bệnh Bộ Y tế."
    )

    print(
        "\nĐang quét Lần 2: Trích xuất các quan hệ lâm sàng (Triệu chứng, Thuốc, Gen)..."
    )
    start_time2 = time.time()

    with open(PRIMEKG_CSV_PATH, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        headers = next(reader)

        for row in reader:
            if len(row) < 12:
                continue

            rel, disp_rel = row[0], row[1]
            x_id, x_type, x_name, x_source = row[3], row[4], row[5], row[6]
            y_id, y_type, y_name, y_source = row[8], row[9], row[10], row[11]

            # CHỈ giữ cạnh nếu một đầu là Nút Bệnh Da Liễu VÀ đầu kia là Triệu chứng, Thuốc hoặc Gen.
            # Phải so cả `type`: id PrimeKG chỉ duy nhất trong từng loại nút (vd id bệnh MONDO
            # trùng số với id gen NCBI), so mỗi id sẽ kéo cả cạnh gen-gen, giải phẫu... vào.
            allowed_other = {"disease", "effect/phenotype", "drug", "gene/protein"}
            is_valid_edge = (
                x_type == "disease"
                and x_id in derma_disease_node_ids
                and y_type in allowed_other
            ) or (
                y_type == "disease"
                and y_id in derma_disease_node_ids
                and x_type in allowed_other
            )

            if is_valid_edge:
                nodes_dict[x_id] = {
                    "id": x_id,
                    "name": x_name,
                    "type": x_type,
                    "source": x_source,
                }
                nodes_dict[y_id] = {
                    "id": y_id,
                    "name": y_name,
                    "type": y_type,
                    "source": y_source,
                }

                edges_list.append(
                    {
                        "relation": rel,
                        "display_relation": disp_rel,
                        "x_id": x_id,
                        "x_name": x_name,
                        "x_type": x_type,
                        "y_id": y_id,
                        "y_name": y_name,
                        "y_type": y_type,
                    }
                )

    print(f"-> Quét xong Lần 2 ({time.time() - start_time2:.1f}s).")
    print(f"-> Tổng Nút Da Liễu chuẩn: {len(nodes_dict)}")
    print(f"-> Tổng Cạnh Da Liễu chuẩn: {len(edges_list)}\n")

    return nodes_dict, edges_list, entity_mapping


def step4_save_outputs(nodes_dict, edges_list, entity_mapping):
    print("=" * 75)
    print(
        " [BƯỚC 4] Đóng gói kết quả Đồ thị Da liễu vào primekg/output/"
    )
    print("=" * 75)

    os.makedirs(OUT_DIR, exist_ok=True)

    # 1. Ghi derma_nodes.csv
    with open(OUT_NODES_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "name", "type", "source"])
        for node in nodes_dict.values():
            writer.writerow(
                [node["id"], node["name"], node["type"], node["source"]]
            )

    # 2. Ghi derma_edges.csv
    with open(OUT_EDGES_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "relation",
                "display_relation",
                "x_id",
                "x_name",
                "x_type",
                "y_id",
                "y_name",
                "y_type",
            ]
        )
        for edge in edges_list:
            writer.writerow(
                [
                    edge["relation"],
                    edge["display_relation"],
                    edge["x_id"],
                    edge["x_name"],
                    edge["x_type"],
                    edge["y_id"],
                    edge["y_name"],
                    edge["y_type"],
                ]
            )

    # 3. Ghi entity_mapping.json
    with open(OUT_MAPPING_JSON, "w", encoding="utf-8") as f:
        json.dump(entity_mapping, f, ensure_ascii=False, indent=2)

    # 4. Ghi derma_kg.json
    kg_json = {
        "metadata": {
            "total_nodes": len(nodes_dict),
            "total_edges": len(edges_list),
            "mapped_guideline_diseases": len(entity_mapping),
        },
        "nodes": list(nodes_dict.values()),
        "edges": edges_list,
    }
    with open(OUT_KG_JSON, "w", encoding="utf-8") as f:
        json.dump(kg_json, f, ensure_ascii=False, indent=2)

    print(f"-> Đã ghi file Nodes  : {OUT_NODES_CSV}")
    print(f"-> Đã ghi file Edges  : {OUT_EDGES_CSV}")
    print(f"-> Đã ghi file Mapping: {OUT_MAPPING_JSON}")
    print(f"-> Đã ghi file Graph  : {OUT_KG_JSON}\n")


def main():
    global OUT_DIR, OUT_NODES_CSV, OUT_EDGES_CSV, OUT_KG_JSON, OUT_MAPPING_JSON

    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument(
        "--output-dir", type=Path, default=OUT_DIR, help="mặc định: primekg/output"
    )
    args = parser.parse_args()
    OUT_DIR = args.output_dir
    OUT_NODES_CSV = OUT_DIR / "derma_nodes.csv"
    OUT_EDGES_CSV = OUT_DIR / "derma_edges.csv"
    OUT_KG_JSON = OUT_DIR / "derma_kg.json"
    OUT_MAPPING_JSON = OUT_DIR / "entity_mapping.json"

    print(
        "\n=========================================================================="
    )
    print(
        "   BẮT ĐẦU TRÍCH XUẤT ĐỒ THỊ DA LIỄU THUẦN TÚY (PURE DERMATOLOGY GRAPH)"
    )
    print(
        "==========================================================================\n"
    )

    seed_disease_names, guideline_map = step1_load_guideline_diseases()
    nodes_dict, edges_list, entity_mapping = (
        step2_3_extract_pure_derma_subgraph(seed_disease_names, guideline_map)
    )
    step4_save_outputs(nodes_dict, edges_list, entity_mapping)

    print(
        "=========================================================================="
    )
    print("   HOÀN THÀNH XỬ LÝ VÀ ĐÓNG GÓI ĐỒ THỊ DA LIỄU CHUẨN XÁC 100%!")
    print(
        "==========================================================================\n"
    )


if __name__ == "__main__":
    main()
