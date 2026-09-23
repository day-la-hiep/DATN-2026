#!/usr/bin/env python3
"""
[Bước 3 trong Pipeline]
Cào nội dung chi tiết (văn bản + danh sách + ảnh) của tất cả các bài viết DermNet Topic liên quan.

Đầu vào:
  - dermnet/output/dermnet_disease_related_topics.json

Đầu ra:
  - dermnet/output/scraped_topics/{slug}/ (article.md & article.json)
"""

import json
import os
import re
import sys
import time
import urllib.request
import urllib.parse

from pathlib import Path

SOURCE_DIR = Path(__file__).resolve().parents[1]  # data-ingest/dermnet
INPUT_DIR = SOURCE_DIR / 'input'
OUTPUT_DIR = SOURCE_DIR / 'output'
BYT_GUIDELINE = SOURCE_DIR.parent / 'byt' / 'output' / 'pdf_guideline_2015.json'

RELATED_TOPICS_PATH = OUTPUT_DIR / 'dermnet_disease_related_topics.json'
OUT_BASE_DIR = OUTPUT_DIR / 'scraped_topics'
PROGRESS_FILE = OUTPUT_DIR / 'pipeline_scrape_progress.json'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
}

def clean_html(text):
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def parse_article(html, url):
    t_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL | re.IGNORECASE)
    title = clean_html(t_match.group(1)) if t_match else 'Untitled'

    clean_content = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    clean_content = re.sub(r'<style[^>]*>.*?</style>', '', clean_content, flags=re.DOTALL | re.IGNORECASE)
    clean_content = re.sub(r'<header[^>]*>.*?</header>', '', clean_content, flags=re.DOTALL | re.IGNORECASE)
    clean_content = re.sub(r'<footer[^>]*>.*?</footer>', '', clean_content, flags=re.DOTALL | re.IGNORECASE)
    clean_content = re.sub(r'<nav[^>]*>.*?</nav>', '', clean_content, flags=re.DOTALL | re.IGNORECASE)

    img_matches = re.findall(r'<img\s+[^>]*src=[\"\']([^\"\']+)[\"\'][^>]*>', clean_content, re.IGNORECASE)
    images = []
    for src in img_matches:
        if any(k in src for k in ['/assets/', 'images', 'upload']) and not any(x in src for x in ['logo', 'icon', 'close', 'advertisement', 'svg']):
            full_img = src if src.startswith('http') else ('https://dermnetnz.org' + src if src.startswith('/') else 'https://dermnetnz.org/' + src)
            if full_img not in images:
                images.append(full_img)

    tokens = re.split(r'(<h[23][^>]*>.*?</h[23]>)', clean_content, flags=re.DOTALL | re.IGNORECASE)
    sections = []
    current_heading = 'Overview'
    current_paragraphs = []
    ignored_headings = ['On DermNet', 'Other websites', 'Books about skin diseases', 'Related information', 'Navigation', 'Main menu']

    for token in tokens:
        h_match = re.match(r'<h([23])[^>]*>(.*?)</h\1>', token, re.DOTALL | re.IGNORECASE)
        if h_match:
            heading_text = clean_html(h_match.group(2))
            if current_paragraphs and current_heading not in ignored_headings:
                body_text = "\n\n".join(current_paragraphs)
                if len(body_text) > 15:
                    sections.append({'heading': current_heading, 'level': 2, 'content': body_text})
            current_heading = heading_text
            current_paragraphs = []
        else:
            paragraphs = re.findall(r'<(?:p|li)[^>]*>(.*?)</(?:p|li)>', token, re.DOTALL | re.IGNORECASE)
            for p in paragraphs:
                cleaned_p = clean_html(p)
                if cleaned_p and not any(noise in cleaned_p.lower() for noise in ['try our skin symptom checker', 'join dermnet pro', 'go to introduction', 'quick links']):
                    current_paragraphs.append(cleaned_p)

    if current_paragraphs and current_heading not in ignored_headings:
        body_text = "\n\n".join(current_paragraphs)
        if len(body_text) > 15:
            sections.append({'heading': current_heading, 'level': 2, 'content': body_text})

    md_lines = [f"# {title}\n", f"**URL:** [{url}]({url})\n", "---\n"]
    for sec in sections:
        md_lines.append(f"## {sec['heading']}\n{sec['content']}\n\n")

    if images:
        md_lines.append("## Image Gallery\n")
        for idx, img in enumerate(images, 1):
            md_lines.append(f"![Image {idx}]({img})\n")

    return {
        'title': title,
        'url': url,
        'sections_count': len(sections),
        'sections': sections,
        'images_count': len(images),
        'images': images,
        'markdown': "\n".join(md_lines)
    }

def scrape_topic(slug, url):
    out_dir = os.path.join(OUT_BASE_DIR, slug)
    os.makedirs(out_dir, exist_ok=True)
    json_path = os.path.join(out_dir, 'article.json')
    md_path = os.path.join(out_dir, 'article.md')

    if os.path.exists(json_path) and os.path.exists(md_path):
        return True, 0  # Đã có dữ liệu trước đó

    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
            data = parse_article(html, url)
            data['slug'] = slug

            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            with open(md_path, 'w', encoding='utf-8') as f:
                f.write(data['markdown'])

            return True, data['sections_count']
    except Exception as e:
        print(f"  [Warn] Lỗi cào {slug} ({url}): {e}")
        return False, 0

def run():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("\n" + "="*70)
    print(" [BƯỚC 3] Cào bài viết từ DermNet theo danh sách Related Topics")
    print("="*70)

    if not os.path.exists(RELATED_TOPICS_PATH):
        print(f"[Lỗi] Không tìm thấy file: {RELATED_TOPICS_PATH}")
        return False

    with open(RELATED_TOPICS_PATH, 'r', encoding='utf-8') as f:
        rel_data = json.load(f)

    topic_map = {}
    for item in rel_data:
        main_topic = item.get('main_topic')
        if main_topic and main_topic.get('slug') and main_topic.get('url'):
            topic_map[main_topic['slug']] = main_topic['url']
        for rt in item.get('related_topics', []):
            if rt.get('slug') and rt.get('url'):
                topic_map[rt['slug']] = rt['url']

    scraped_slugs = set()
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
            scraped_slugs = set(json.load(f))

    remaining = [(slug, url) for slug, url in topic_map.items() if slug not in scraped_slugs]
    print(f"Tổng số topic độc nhất cần cào: {len(topic_map)}")
    print(f"Đã cào thành công trước đó     : {len(scraped_slugs)}")
    print(f"Còn lại cần cào                : {len(remaining)}\n")

    success_cnt = 0
    for idx, (slug, url) in enumerate(remaining, 1):
        print(f"[{idx}/{len(remaining)}] Scraping: {slug}...")
        ok, sec_cnt = scrape_topic(slug, url)
        if ok:
            success_cnt += 1
            scraped_slugs.add(slug)
            with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
                json.dump(list(scraped_slugs), f, ensure_ascii=False, indent=2)
        time.sleep(0.3)

    print(f"-> Cào hoàn tất! Đã lưu {len(scraped_slugs)}/{len(topic_map)} bài viết vào {OUT_BASE_DIR}\n")
    return True

if __name__ == '__main__':
    sys.exit(0 if run() else 1)
