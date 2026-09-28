#!/usr/bin/env python3
"""
[Bước 5 trong Pipeline]
Phân loại các bài viết topic DermNet cào được vào đúng thư mục con:
dermnet/output/post/{disease_id}/related_topics/{slug}/
  ├── article.md
  └── article.json
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

RELATED_TOPICS_PATH = OUTPUT_DIR / 'dermnet_disease_related_topics.json'
SCRAPED_BASE_DIR = OUTPUT_DIR / 'scraped_topics'
POST_BASE_DIR = OUTPUT_DIR / 'post'

def run():
    print("\n" + "="*70)
    print(" [BƯỚC 5] Tổ chức phân loại các bài viết topic cào được vào post/{disease_id}/related_topics/")
    print("="*70)

    if not os.path.exists(RELATED_TOPICS_PATH):
        print(f"[Lỗi] Không tìm thấy file: {RELATED_TOPICS_PATH}")
        return False

    with open(RELATED_TOPICS_PATH, 'r', encoding='utf-8') as f:
        rel_data = json.load(f)

    total_copied = 0
    diseases_processed = 0

    for item in rel_data:
        disease_id = item['disease_id']
        disease_post_dir = os.path.join(POST_BASE_DIR, disease_id)
        target_rel_dir = os.path.join(disease_post_dir, 'related_topics')
        os.makedirs(target_rel_dir, exist_ok=True)

        disease_slugs = []
        main_topic = item.get('main_topic')
        if main_topic and main_topic.get('slug'):
            disease_slugs.append(main_topic['slug'])

        for rt in item.get('related_topics', []):
            if rt.get('slug') and rt['slug'] not in disease_slugs:
                disease_slugs.append(rt['slug'])

        for slug in disease_slugs:
            src_topic_dir = os.path.join(SCRAPED_BASE_DIR, slug)
            if os.path.exists(src_topic_dir):
                dest_topic_dir = os.path.join(target_rel_dir, slug)
                os.makedirs(dest_topic_dir, exist_ok=True)

                for fname in ['article.md', 'article.json']:
                    src_file = os.path.join(src_topic_dir, fname)
                    if os.path.exists(src_file):
                        shutil.copy2(src_file, os.path.join(dest_topic_dir, fname))
                total_copied += 1

        diseases_processed += 1

    print(f"-> Phân loại thành công {total_copied} bài viết topic vào đúng {diseases_processed} thư mục bệnh lý!\n")
    return True

if __name__ == '__main__':
    sys.exit(0 if run() else 1)
