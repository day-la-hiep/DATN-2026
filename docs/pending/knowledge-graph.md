# [Pending] Cải thiện nhánh Knowledge Graph

Nhánh KG của `hybrid_retrieval` / `knowledge_graph_search` (`core/agent/tools/hybrid_retrieval/kg.py`,
`core/app/services/knowledge_graph_service.py`) chạy được nhưng còn đơn giản. Tài liệu này ghi các điểm chưa làm để
chọn việc khi còn thời gian; không phải cam kết.

## 1. Việc chưa làm (theo mức ảnh hưởng)

| # | Việc | Vì sao | Gợi ý cách làm |
|---|---|---|---|
| 1 | **Trực quan hoá KG theo bệnh nhân (M8.3)** | Yêu cầu còn thiếu trong [requirements.md](../overview/requirements.md) | API trả subgraph quanh thực thể của bệnh nhân (từ clinical fact M3.1) + thư viện vẽ graph ở FE |
| 2 | **Khớp thực thể tiếng Việt ngay trên đồ thị** | KG chỉ khớp tên tiếng Anh; việc dịch phụ thuộc hoàn toàn vào một lần gọi LLM, LLM yếu thì dịch sai là mất cả nhánh | Bảng alias Việt → Anh/DermO (từ DermO synonyms + `dermo_terms`, bổ sung tay các bệnh thường gặp) tra trước khi hỏi LLM |
| 3 | **Khớp tên bằng `CONTAINS`** | `_PRIMEKG_SEARCH_QUERY` dùng `toLower(n.name) CONTAINS ...`: có thể ra thực thể không liên quan ("acne" ra cả tên dài chứa "acne") và không dùng index | Ưu tiên khớp chính xác (`exact_dermo`) rồi mới `CONTAINS`; hoặc full-text index của Neo4j |
| 4 | **Điểm bệnh ứng viên là heuristic** | Trọng số `3 / ln(2 + degree)` và trần 2-hop chưa được kiểm chứng với ca thật | Bộ ca có đáp án để chỉnh trọng số; so thứ hạng với chẩn đoán của bác sĩ |
| 5 | **Chưa dùng chống chỉ định / tác dụng phụ của thuốc để kiểm tra đơn** | Quan hệ `CONTRAINDICATION` đã nạp nhưng chỉ hiện như một câu quan hệ | Tool kiểm tra thuốc vs tiền sử/dị ứng của bệnh nhân (`patient_profile`) |
| 6 | **Chỉ giữ 6 loại quan hệ lâm sàng** | `_RELATION_LABELS` loại bỏ quan hệ phân tử/tế bào (gen, protein) nên chưa trả lời được câu hỏi cơ chế | Thêm `DISEASE_PROTEIN`, `DRUG_PROTEIN`... khi có nhu cầu giải thích cơ chế |
| 7 | **KG và sách giáo khoa chưa liên kết** | Cùng một bệnh nhưng đoạn sách và nút KG không biết nhau; chỉ gặp nhau ở bước rerank | Gắn `dermo_id`/tên chuẩn vào payload chunk lúc `index` để lọc và trích nguồn chéo |
| 8 | **Đánh giá chất lượng** | Chưa có số đo cho nhánh KG (chọn đúng thực thể? ứng viên đúng bao nhiêu?) | Bộ câu hỏi nhỏ có đáp án + script đo (xem `agent/test/try_retrieval.py`) |
| 9 | **Nạp lại KG** | Script nạp cũ (`load_knowledge_base.py`, `04_link_dermo_ids.py`) đã bỏ; còn `load_primekg.py`, `load_dermo.py` | Ghi thứ tự nạp + cách kiểm tra dữ liệu trong `data_ingest/README.md` |
| 10 | **Neo4j là phụ thuộc cứng của nhánh KG** | Neo4j chưa chạy thì nhánh KG báo `notes` và mất ứng viên chẩn đoán | Đã chịu lỗi từng nhánh; có thể thêm cache các truy vấn phổ biến |

## 2. Ràng buộc cần giữ

- Kết quả KG chỉ là **gợi ý**, không phải bằng chứng lâm sàng và không phải chẩn đoán: `hybrid_retrieval` đã báo
  `evidence_found=false` khi chỉ có KG mà không có đoạn sách, giữ nguyên hành vi này.
- Thay đổi dữ liệu KG không được làm mất dữ liệu đã nạp (nạp lại phải idempotent).
- Entity nghiệp vụ nằm ở `core/app/dto/base/`; nếu cần entity mới (vd cho M8.3) phải hỏi duyệt trước.
