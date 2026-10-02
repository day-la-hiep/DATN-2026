# dhyd — Đại học Y Dược TP.HCM - Bệnh da liễu thường gặp (2020)

36 bệnh lý và chủ đề lâm sàng trọng điểm được trích xuất từ giáo trình chính thức *Bệnh da liễu thường gặp* (Chủ biên: PGS.TS.BS. Văn Thế Trung - Bộ môn Da liễu, Đại học Y Dược TP. Hồ Chí Minh, NXB Y Học, 2020, 248 trang, Quyết định số 1832/QĐ-ĐHYD).

Nguồn cung cấp căn cứ chẩn đoán lâm sàng, dịch tễ học và tiếp cận xử trí theo chuẩn đào tạo bác sĩ đa khoa và chuyên khoa Da liễu Việt Nam. Bao gồm 13 chương toàn diện: Phát ban dạng chàm, Viêm da cơ địa, Mày đay, Mụn trứng cá, Bệnh da do nhiễm (vi khuẩn, virus, nấm, ký sinh trùng), Vảy nến, Bệnh bóng nước tự miễn, Phản ứng da do thuốc thể nặng (SJS/TEN, DRESS, AGEP), Tiếp cận bệnh nhân ngứa, Bệnh lây truyền qua đường tình dục (STDs), Bệnh lý niêm mạc miệng, Chăm sóc bệnh nhân da liễu và Nguyên tắc sử dụng thuốc thoa.

| | |
|---|---|
| **Input** | `Đại học y dược TP HCM - Bệnh da liễu thường gặp.pdf` (gốc ở thư mục root repo, 249 trang scan) |
| **Scripts** | `01_extract_toc.py` (Lập chỉ mục mục lục 13 chương và các bệnh, chuẩn hóa bù lệch trang PDF)<br>`02_build_guidelines.py` (Trích xuất, cấu trúc hóa JSON theo schema chuẩn của hệ thống DATN)<br>`03_build_chunks.py` (Tạo vector chunks 5 loại: overview, symptoms, differential, advice, risk) |
| **Output** | `output/dhyd_toc.json` (Mục lục chi tiết 13 chương và 36 mục con)<br>`output/dhyd_diseases.json` (36 bản ghi bệnh lý theo schema chuẩn)<br>`output/dhyd_chunks.json` (180 vector chunks định dạng chuẩn Qdrant KB) |

## Schema
Tất cả các bản ghi tuân thủ schema chuẩn:
- `id`: có hậu tố `_dhyd` (ví dụ: `viem_da_co_dia_dhyd`, `benh_vay_nen_dhyd`, `hoi_chung_stevens_johnson_ten_dhyd`,...).
- `name`, `english_name`, `type`, `summary`, `common_features`, `suggestive_phrases`, `typical_locations`, `course`, `risk_factors`, `differential_diagnoses`, `differential_diagnosis_details`, `red_flags`, `safe_advice`.
- `references`: ghi rõ `source_id: "dhyd_2020"`, số trang sách `page_start`, số trang scan `pdf_page_start`, nhà xuất bản Y Học và năm 2020.
- `medical_review_status`: `"needs_clinical_review"`.
