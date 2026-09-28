#!/usr/bin/env python3
"""
[Bước 2 trong Pipeline]
Đọc dữ liệu 65 bệnh da liễu Bộ Y tế (pdf_guideline_2015.json)
và tự động ánh xạ tới bài viết chính + các topic DermNet liên quan.

Đầu vào:
  - byt/output/pdf_guideline_2015.json
  - dermnet/output/dermnet_topics.json

Đầu ra:
  - dermnet/output/dermnet_disease_related_topics.json
  - dermnet/output/dermnet_disease_related_topics.csv
"""

import json
import os
import sys
import re
import csv

from pathlib import Path

SOURCE_DIR = Path(__file__).resolve().parents[1]  # data-ingest/dermnet
INPUT_DIR = SOURCE_DIR / 'input'
OUTPUT_DIR = SOURCE_DIR / 'output'
BYT_GUIDELINE = SOURCE_DIR.parent / 'byt' / 'output' / 'pdf_guideline_2015.json'

BYT_GUIDELINE_PATH = BYT_GUIDELINE
DERMNET_TOPICS_PATH = OUTPUT_DIR / 'dermnet_topics.json'
OUT_JSON_PATH = OUTPUT_DIR / 'dermnet_disease_related_topics.json'
OUT_CSV_PATH = OUTPUT_DIR / 'dermnet_disease_related_topics.csv'

def run():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("\n" + "="*70)
    print(" [BƯỚC 2] Ánh xạ Bệnh Bộ Y tế ➔ Bài viết Topic DermNet liên quan")
    print("="*70)

    if not os.path.exists(BYT_GUIDELINE_PATH):
        print(f"[Lỗi] Không tìm thấy file: {BYT_GUIDELINE_PATH}")
        return False
    if not os.path.exists(DERMNET_TOPICS_PATH):
        print(f"[Lỗi] Không tìm thấy file: {DERMNET_TOPICS_PATH}")
        return False

    with open(BYT_GUIDELINE_PATH, 'r', encoding='utf-8') as f:
        byt_diseases = json.load(f)

    with open(DERMNET_TOPICS_PATH, 'r', encoding='utf-8') as f:
        dermnet_topics = json.load(f)

    topic_by_slug = {t['slug']: t for t in dermnet_topics}
    topic_by_title_lower = {t['title'].lower(): t for t in dermnet_topics}
    alt_title_map = {}
    for t in dermnet_topics:
        for alt in t.get('alt_titles', []):
            alt_title_map[alt.lower()] = t

    mapped_results = []

    for disease in byt_diseases:
        disease_id = disease['id']
        name_vi = disease['name']
        name_en = disease.get('english_name', '').strip()
        chapter = disease.get('type', '')
        diff_diag_slugs = disease.get('differential_diagnoses', [])

        main_topic = topic_by_title_lower.get(name_en.lower()) or alt_title_map.get(name_en.lower())
        if not main_topic:
            slug_guess = name_en.lower().replace(' ', '-').replace('(', '').replace(')', '')
            main_topic = topic_by_slug.get(slug_guess)

        words = [w for w in re.split(r'[\s\-/]+', name_en.lower()) if len(w) > 3 and w not in ['disease', 'syndrome', 'infection', 'type', 'with', 'from', 'skin', 'acute', 'chronic', 'inherited']]

        related_topics = []
        seen_urls = set()
        if main_topic:
            seen_urls.add(main_topic['url'])

        for topic in dermnet_topics:
            if topic['url'] in seen_urls:
                continue

            topic_text = (topic['title'] + ' ' + ' '.join(topic.get('alt_titles', []))).lower()
            match_keyword = any(w in topic_text for w in words)
            match_diff = any(dd_slug.replace('_', '-') in topic['slug'] for dd_slug in diff_diag_slugs)

            if match_keyword or match_diff:
                seen_urls.add(topic['url'])
                related_topics.append({
                    'title': topic['title'],
                    'url': topic['url'],
                    'slug': topic['slug'],
                    'alt_titles': topic.get('alt_titles', [])
                })

        mapped_results.append({
            'disease_id': disease_id,
            'name_vi': name_vi,
            'name_en': name_en,
            'chapter': chapter,
            'main_topic': main_topic,
            'related_topics_count': len(related_topics),
            'related_topics': related_topics
        })

    with open(OUT_JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(mapped_results, f, ensure_ascii=False, indent=2)

    with open(OUT_CSV_PATH, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['disease_id', 'name_vi', 'name_en', 'chapter', 'main_topic_url', 'related_topics_count', 'related_topics_titles'])
        for r in mapped_results:
            main_url = r['main_topic']['url'] if r['main_topic'] else ''
            rel_titles = ' | '.join([t['title'] for t in r['related_topics']])
            writer.writerow([
                r['disease_id'],
                r['name_vi'],
                r['name_en'],
                r['chapter'],
                main_url,
                r['related_topics_count'],
                rel_titles
            ])

    print(f"-> Ánh xạ thành công bài viết liên quan cho {len(mapped_results)} bệnh lý!")
    print(f"   [File xuất JSON]: {OUT_JSON_PATH}\n")
    return True

if __name__ == '__main__':
    sys.exit(0 if run() else 1)
