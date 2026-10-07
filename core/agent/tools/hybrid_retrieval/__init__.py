"""Package tra cứu tri thức y khoa — expose cho agent 1 tool tổng hợp và 3 tool chuyên biệt, model tự chọn / phối hợp:

  - `hybrid_retrieval`       : MẶC ĐỊNH cho yêu cầu chung — chạy song song cả 3 nhánh dưới đây, trộn RRF hai nhánh chunk rồi
                               rerank chung; một lần gọi cho kết quả sách + đồ thị;

  - `semantic_search`        : embedding local (`agent/embeddings.py`) -> Qdrant, chunk sách của pipeline `document_ingest`;
  - `keyword_search`         : chỉ mục BM25 trong bộ nhớ trên chính các chunk đó (`bm25.py`) — bắt tên thuốc, mã, thuật ngữ mà
                               embedding hay bỏ lỡ;
  - `knowledge_graph_search` : PrimeKG / DermO (`kg.py`) — quan hệ bệnh–triệu chứng–thuốc và bệnh ứng viên.

Tool chuyên biệt dành cho lúc đã lập luận rõ cần đúng loại thông tin nào (khớp tên thuốc, chỉ cần quan hệ đồ thị...).
Hai tool sách rerank kết quả bằng cross-encoder (`reranker.py`); không rerank được thì giữ thứ tự của nhánh. Mỗi tool tự bắt lỗi
hạ tầng của mình (Neo4j / Qdrant chưa chạy...) và trả ghi chú trong `notes`, không làm hỏng cả lượt. Bằng chứng để trích dẫn chỉ là
đoạn sách (`source="book"`); kết quả đồ thị (`source="kg"`) chỉ là gợi ý.

Kết quả là bằng chứng để trích dẫn, KHÔNG phải chẩn đoán y khoa.

Các file:
  - `tool.py`      — 4 tool trên;
  - `semantic.py`  — nhánh semantic (embedding -> Qdrant);
  - `bm25.py`      — nhánh từ khoá, chỉ mục BM25 trong bộ nhớ;
  - `kg.py`        — nhánh đồ thị tri thức (PrimeKG / DermO);
  - `fusion.py`    — trộn thứ hạng (RRF) và dựng kết quả sách;
  - `reranker.py`  — cross-encoder chấm lại ứng viên.
"""
from agent.tools.hybrid_retrieval.tool import hybrid_retrieval, keyword_search, knowledge_graph_search, semantic_search

__all__ = ["hybrid_retrieval", "keyword_search", "knowledge_graph_search", "semantic_search"]
