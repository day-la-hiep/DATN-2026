#!/usr/bin/env python3
"""
[Bước 1 trong Pipeline]
Trích xuất danh mục 2,419 bài viết Topic DermNet (A-Z) từ file HTML snapshot.

Đầu vào:
  - dermnet/input/skin_info.html

Đầu ra:
  - dermnet/output/dermnet_topics.json
  - dermnet/output/dermnet_topics.csv
"""

import os
import sys
import re
import json
import csv

from pathlib import Path

SOURCE_DIR = Path(__file__).resolve().parents[1]  # data-ingest/dermnet
INPUT_DIR = SOURCE_DIR / 'input'
OUTPUT_DIR = SOURCE_DIR / 'output'
BYT_GUIDELINE = SOURCE_DIR.parent / 'byt' / 'output' / 'pdf_guideline_2015.json'

HTML_PATH = INPUT_DIR / 'skin_info.html'
OUT_JSON_PATH = OUTPUT_DIR / 'dermnet_topics.json'
OUT_CSV_PATH = OUTPUT_DIR / 'dermnet_topics.csv'

def run():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("\n" + "="*70)
    print(" [BƯỚC 1] Trích xuất danh mục bài viết DermNet (A-Z Index)")
    print("="*70)

    if not HTML_PATH.exists():
        print(f"[Lỗi] Không tìm thấy file: {HTML_PATH}")
        return False

    print(f"Đang đọc file HTML: {HTML_PATH}...")
    with open(HTML_PATH, 'r', encoding='utf-8') as f:
        content = f.read()

    letter_pattern = r'<h[234][^>]*>\s*([A-Z])\s*</h[234]>(.*?)(?=(?:<h[234][^>]*>\s*[A-Z]\s*</h[234]>|<footer>|<footer|</body>))'
    matches = re.findall(letter_pattern, content, re.DOTALL | re.IGNORECASE)

    url_to_info = {}

    for letter, block in matches:
        letter = letter.upper()
        links = re.findall(r'<a\s+[^>]*href=[\"\']([^\"\']+)[\"\'][^>]*>(.*?)</a>', block, re.DOTALL | re.IGNORECASE)
        
        for href, text in links:
            clean_text = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', text)).strip()
            if not clean_text or clean_text.lower() in ['back to top', 'top', 'topics a-z']:
                continue

            if '/topics/' in href or 'topics/' in href:
                full_url = href if href.startswith('http') else ('https://dermnetnz.org' + href if href.startswith('/') else 'https://dermnetnz.org/' + href)
                slug = full_url.rstrip('/').split('/')[-1]
                
                if full_url not in url_to_info:
                    url_to_info[full_url] = {
                        'title': clean_text,
                        'url': full_url,
                        'slug': slug,
                        'letter': letter,
                        'alt_titles': []
                    }
                else:
                    if clean_text != url_to_info[full_url]['title'] and clean_text not in url_to_info[full_url]['alt_titles']:
                        url_to_info[full_url]['alt_titles'].append(clean_text)

    topics_list = sorted(list(url_to_info.values()), key=lambda x: x['title'].lower())

    with open(OUT_JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(topics_list, f, ensure_ascii=False, indent=2)

    with open(OUT_CSV_PATH, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['slug', 'title', 'letter', 'url', 'alt_titles'])
        for t in topics_list:
            writer.writerow([t['slug'], t['title'], t['letter'], t['url'], ' | '.join(t['alt_titles'])])

    print(f"-> Trích xuất thành công {len(topics_list)} bài viết topic DermNet (A-Z)!")
    print(f"   [File xuất JSON]: {OUT_JSON_PATH}\n")
    return True

if __name__ == '__main__':
    sys.exit(0 if run() else 1)
