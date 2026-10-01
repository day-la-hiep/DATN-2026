# andrews — Andrews' Diseases of the Skin (12th Edition, 2015)


49 bệnh da liễu phổ biến được trích xuất từ sách giáo khoa kinh điển *Andrews' Diseases of the Skin: Clinical Dermatology* (James, Berger, Elston - 12th ed., Elsevier, 2015, 1.083 trang) dựa trên việc đối chiếu với danh mục 65 bệnh mốc của Bộ Y tế Việt Nam.

Nguồn cung cấp căn cứ lâm sàng và bằng chứng học thuật quốc tế chuyên sâu, đặc biệt nổi bật ở các tiêu chí chẩn đoán phân biệt (*Differential Diagnosis*), hình thái tổn thương và dấu hiệu cảnh báo đỏ (*Red Flags*). Các bệnh tiêu biểu gồm: acne vulgaris, atopic dermatitis, psoriasis, scabies, impetigo, herpes zoster, urticaria, rosacea, alopecia areata, melanoma...

| | |
|---|---|
| Input | `Andrews_Diseases_of_the_Skin_-_Clinical_Dermatology_2015.pdf` (gốc ở thư mục root repo, ~79MB, không commit) |
| Scripts | `01_extract_toc.py` (Giai đoạn 1: bóc tách mục lục, lập chỉ mục trang theo bệnh) <br> `02_build_guidelines.py` (Giai đoạn 2: trích xuất text và cấu trúc hóa JSON theo schema) |
| Output | `output/andrews_toc.json` (3.440 mục lục chi tiết)<br>`output/andrews_diseases.json` |

## Pipeline

- `01_extract_toc.py`: Quét toàn bộ Bookmark/TOC từ file PDF, xác định số trang `start_page` và `end_page` của từng bệnh/chương.
- `02_build_guidelines.py`: Trích xuất text từ các trang tương ứng, bóc tách và chuẩn hóa sang schema chung của dự án (`id`, `name`, `english_name`, `type`, `summary`, `common_features`, `suggestive_phrases`, `typical_locations`, `course`, `risk_factors`, `differential_diagnoses`, `differential_diagnosis_details`, `red_flags`, `safe_advice`, `references`).

`id` có hậu tố `_andrews`. Trạng thái duyệt: `needs_manual_verification`.