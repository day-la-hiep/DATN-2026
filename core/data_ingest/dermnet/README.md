# dermnet — DermNet (dermnetnz.org)

Lập chỉ mục các bài "topic" của DermNet, ánh xạ 65 bệnh BYT sang bài liên quan, cào nội dung và dựng
thư mục bài viết cho từng bệnh. Dùng làm nguồn tham khảo/hình ảnh; **chưa được `normalize` gom** và
`core/` chưa đọc trực tiếp.

| | |
|---|---|
| Input | `input/skin_info.html` (snapshot mục lục A–Z) + `../byt/output/pdf_guideline_2015.json` |
| Output | `output/` (xem bảng dưới) |

## Scripts (chạy theo thứ tự: `python ../run.py dermnet`)

| Script | Việc | Output |
|---|---|---|
| `01_extract_topics_index.py` | parse HTML -> 2.419 topic | `dermnet_topics.{json,csv}` |
| `02_map_byt_to_related_topics.py` | mỗi bệnh BYT -> topic chính + topic liên quan (65 bệnh) | `dermnet_disease_related_topics.{json,csv}` |
| `03_scrape_related_topics.py` | **cào web** nội dung từng topic (resume được qua `pipeline_scrape_progress.json`) | `scraped_topics/{slug}/article.{md,json}` (~1.019 topic) |
| `04_build_disease_posts.py` | dựng bài tổng quan mỗi bệnh | `post/{disease_id}/{article.md, bài_viết.md, data.json, images/}` |
| `05_organize_topics_per_disease.py` | chép topic đã cào vào từng bệnh | `post/{disease_id}/related_topics/{slug}/` |

Mỗi script trả exit code ≠ 0 khi lỗi nên `run.py` dừng đúng chỗ.

## Lưu ý

- `scraped_topics/` và `post/` (~140MB) bị `.gitignore`, tái tạo bằng `run.py dermnet`; bước 03 cần mạng và chạy lâu.
- Nội dung DermNet có bản quyền của DermNet NZ — chỉ dùng để tham khảo nội bộ, không phát hành lại.
