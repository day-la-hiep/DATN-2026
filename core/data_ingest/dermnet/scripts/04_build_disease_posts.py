#!/usr/bin/env python3
"""
[Bước 4 trong Pipeline]
Sinh thư mục bài viết gốc cho từng bệnh lý tại dermnet/output/post/{disease_id}/:
  ├── article.md
  ├── bài_viết.md
  ├── data.json
  └── images/
"""

import json
import os
import sys
import shutil

from pathlib import Path

SOURCE_DIR = Path(__file__).resolve().parents[1]  # data-ingest/dermnet
INPUT_DIR = SOURCE_DIR / 'input'
OUTPUT_DIR = SOURCE_DIR / 'output'
BYT_GUIDELINE = SOURCE_DIR.parent / 'byt' / 'output' / 'pdf_guideline_2015.json'

GUIDELINE_PATH = BYT_GUIDELINE
RELATED_TOPICS_PATH = OUTPUT_DIR / 'dermnet_disease_related_topics.json'
POST_BASE_DIR = OUTPUT_DIR / 'post'

def run():
    print("\n" + "="*70)
    print(" [BƯỚC 4] Sinh thư mục bài viết tổng quan bệnh lý (post/{disease_id}/)")
    print("="*70)

    if not os.path.exists(GUIDELINE_PATH):
        print(f"[Lỗi] Không tìm thấy file: {GUIDELINE_PATH}")
        return False

    with open(GUIDELINE_PATH, 'r', encoding='utf-8') as f:
        byt_diseases = json.load(f)

    related_map = {}
    if os.path.exists(RELATED_TOPICS_PATH):
        with open(RELATED_TOPICS_PATH, 'r', encoding='utf-8') as f:
            rel_data = json.load(f)
            related_map = {item['disease_id']: item for item in rel_data}

    count = 0
    for disease in byt_diseases:
        disease_id = disease['id']
        name_vi = disease['name']
        name_en = disease.get('english_name', '')
        chapter = disease.get('type', '')
        summary = disease.get('summary', '')
        common_features = disease.get('common_features', [])
        suggestive_phrases = disease.get('suggestive_phrases', [])
        locations = disease.get('typical_locations', [])
        course = disease.get('course', '')
        risk_factors = disease.get('risk_factors', [])
        diff_diag = disease.get('differential_diagnoses', [])
        diff_details = disease.get('differential_diagnosis_details', '')
        red_flags = disease.get('red_flags', [])
        safe_advice = disease.get('safe_advice', [])
        references = disease.get('references', [])

        rel_info = related_map.get(disease_id, {})
        main_topic = rel_info.get('main_topic')
        related_topics = rel_info.get('related_topics', [])

        disease_dir = os.path.join(POST_BASE_DIR, disease_id)
        os.makedirs(disease_dir, exist_ok=True)

        md = []
        md.append(f"# {name_vi} ({name_en})\n")
        md.append(f"**Chương / Phân loại:** {chapter}\n")
        md.append(f"**Mã định danh:** `{disease_id}`\n")
        if main_topic:
            md.append(f"**Bài viết gốc DermNet:** [{main_topic.get('title', name_en)}]({main_topic.get('url', '')})\n")

        md.append("\n---\n")

        md.append(f"## 1. Tổng quan\n{summary}\n\n")

        md.append("## 2. Đặc điểm lâm sàng & Triệu chứng thường gặp\n")
        if common_features:
            for feat in common_features:
                md.append(f"- `{feat}`")
            md.append("\n")
        if suggestive_phrases:
            phrases_str = ", ".join([f"*{p}*" for p in suggestive_phrases])
            md.append(f"\n**Cụm từ gợi ý chẩn đoán:** {phrases_str}\n")
        md.append("\n")

        md.append("## 3. Vị trí tổn thương thường gặp\n")
        if locations:
            for loc in locations:
                md.append(f"- {loc}")
            md.append("\n")

        md.append(f"## 4. Diễn tiến bệnh\n{course}\n\n")

        md.append("## 5. Yếu tố nguy cơ\n")
        if risk_factors:
            for rf in risk_factors:
                md.append(f"- {rf}")
            md.append("\n")

        md.append("## 6. Chẩn đoán phân biệt\n")
        if diff_diag:
            dd_str = ", ".join([f"`{dd}`" for dd in diff_diag])
            md.append(f"**Các bệnh cần phân biệt:** {dd_str}\n\n")
        if diff_details:
            md.append(f"**Mô tả phân biệt chi tiết:**\n{diff_details}\n\n")

        md.append("## 7. Dấu hiệu cảnh báo nguy hiểm (Red Flags)\n")
        if red_flags:
            for rf in red_flags:
                md.append(f"- ⚠️ {rf}")
            md.append("\n")

        md.append("## 8. Hướng dẫn xử trí & Lời khuyên an toàn\n")
        if safe_advice:
            for idx_sa, sa in enumerate(safe_advice, 1):
                md.append(f"{idx_sa}. {sa}")
            md.append("\n")

        md.append("## 9. Bài viết Topic DermNet liên quan\n")
        for rt in related_topics[:15]:
            md.append(f"- [{rt['title']}]({rt['url']})")
        md.append("\n")

        md_content = "\n".join(md)
        with open(os.path.join(disease_dir, 'article.md'), 'w', encoding='utf-8') as f_md:
            f_md.write(md_content)

        with open(os.path.join(disease_dir, 'bài_viết.md'), 'w', encoding='utf-8') as f_md:
            f_md.write(md_content)

        count += 1

    print(f"-> Tạo hoàn tất thư mục bài viết gốc cho {count} bệnh lý!\n")
    return True

if __name__ == '__main__':
    sys.exit(0 if run() else 1)
