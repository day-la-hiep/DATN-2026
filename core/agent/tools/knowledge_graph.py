"""Tool tra cứu knowledge graph da liễu — dữ liệu PrimeKG đã lọc/nạp sẵn vào Neo4j
(`data/PrimeKG/load_to_neo4j.py`, xem `data/PrimeKG/process_dermatology_kg.py` cho bước
lọc). Dùng THẲNG `langchain-neo4j` (`Neo4jGraph` + `GraphCypherQAChain`) — LLM tự sinh
Cypher từ câu hỏi tự nhiên rồi chạy trên Neo4j, không tự viết logic truy vấn/sinh query
riêng — đúng tinh thần ưu tiên framework có sẵn đã thống nhất cho cả module `agent/`.

Schema đưa cho LLM sinh Cypher (`_EXCLUDE_TYPES`) bỏ bớt các loại node/quan hệ mức phân
tử (protein-protein interaction, anatomy-protein, pathway, bioprocess/molfunc/cellcomp
nội bộ...) — dữ liệu đó VẪN nằm đủ trong Neo4j (toàn bộ ~474k cạnh đã nạp), chỉ không
hiện trong prompt sinh Cypher để tránh nhiễu/tốn token cho các câu hỏi tư vấn da liễu
thông thường (bệnh/triệu chứng/thuốc/chỉ định-chống chỉ định).

An toàn: Neo4j Community Edition không có RBAC (không tạo được user chỉ-đọc riêng như
Enterprise) — `ReadOnlyNeo4jGraph` chặn Cypher có từ khoá ghi (CREATE/MERGE/DELETE/SET/
REMOVE/DROP...) ở tầng ứng dụng trước khi thực thi, phòng LLM sinh nhầm Cypher ghi đè dữ
liệu tham khảo tĩnh này.
"""
import re
from typing import Any

from langchain_core.prompts.prompt import PromptTemplate
from langchain_core.tools import tool
from langchain_neo4j import GraphCypherQAChain, Neo4jGraph
from langchain_neo4j.chains.graph_qa.prompts import CYPHER_GENERATION_PROMPT

from agent.llm import get_model
from app.core.config import settings

# Dữ liệu gốc PrimeKG đặt tên node theo THỂ BỆNH CỤ THỂ (vd "guttate psoriasis",
# "pustular psoriasis"), hiếm khi có node tên đúng dạng chung chung (vd không có node
# tên "psoriasis" trần) — Cypher LLM sinh mặc định hay match CHÍNH XÁC (`{name:
# 'psoriasis'}`) sẽ ra rỗng dù dữ liệu liên quan có tồn tại. Thêm hướng dẫn + ví dụ dùng
# `CONTAINS` (đã verify thực tế bằng test thủ công — xem lịch sử trao đổi) để LLM tự sinh
# match kiểu gần đúng thay vì so khớp tuyệt đối.
_CYPHER_GENERATION_TEMPLATE = (
    CYPHER_GENERATION_PROMPT.template
    + "\n\nLưu ý QUAN TRỌNG: tên node trong dữ liệu này thường là thể bệnh/thực thể CỤ "
    "THỂ (vd \"guttate psoriasis\" thay vì \"psoriasis\"), KHÔNG so khớp tuyệt đối "
    "`{{name: 'psoriasis'}}` — dùng `toLower(n.name) CONTAINS toLower('psoriasis')` để "
    "bắt được mọi thể bệnh liên quan. Ví dụ:\n"
    "MATCH (d:Drug)-[r:CONTRAINDICATION]->(dis:Disease) "
    "WHERE toLower(dis.name) CONTAINS toLower('psoriasis') RETURN d.name, dis.name"
)
_CYPHER_GENERATION_PROMPT = PromptTemplate(
    input_variables=CYPHER_GENERATION_PROMPT.input_variables,
    template=_CYPHER_GENERATION_TEMPLATE,
)

_WRITE_CLAUSE_RE = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|CALL\s+apoc\.(create|refactor|periodic))\b",
    re.IGNORECASE,
)

# Loại node/quan hệ mức phân tử/tế bào — không cần cho câu hỏi tư vấn da liễu thông
# thường (bệnh/triệu chứng/thuốc), chỉ làm nhiễu schema đưa cho Cypher-generation LLM.
_EXCLUDE_TYPES = [
    "PROTEIN_PROTEIN",
    "ANATOMY_PROTEIN_PRESENT",
    "ANATOMY_PROTEIN_ABSENT",
    "BIOPROCESS_PROTEIN",
    "MOLFUNC_PROTEIN",
    "CELLCOMP_PROTEIN",
    "PATHWAY_PROTEIN",
    "BIOPROCESS_BIOPROCESS",
    "MOLFUNC_MOLFUNC",
    "CELLCOMP_CELLCOMP",
    "ANATOMY_ANATOMY",
    "EXPOSURE_PROTEIN",
    "EXPOSURE_BIOPROCESS",
    "EXPOSURE_MOLFUNC",
    "GeneProtein",
    "Anatomy",
    "BiologicalProcess",
    "MolecularFunction",
    "CellularComponent",
    "Pathway",
    "Exposure",
]


class ReadOnlyNeo4jGraph(Neo4jGraph):
    """`Neo4jGraph` chặn Cypher có từ khoá ghi — xem docstring module."""

    def query(self, query: str, params: dict[str, Any] | None = None, session_params: dict[str, Any] | None = None) -> list[dict[str, Any]]:  # type: ignore[override]
        if _WRITE_CLAUSE_RE.search(query):
            raise ValueError(
                f"Cypher bị từ chối (có từ khoá ghi, chỉ cho phép đọc): {query!r}"
            )
        return super().query(query, params or {}, session_params or {})  # pyright: ignore[reportUnknownMemberType]


_kg_chain: GraphCypherQAChain | None = None


def _get_chain() -> GraphCypherQAChain:
    global _kg_chain
    if _kg_chain is None:
        graph = ReadOnlyNeo4jGraph(
            url=settings.NEO4J_URL,
            username=settings.NEO4J_USER,
            password=settings.NEO4J_PASSWORD,
        )
        _kg_chain = GraphCypherQAChain.from_llm(  # pyright: ignore[reportUnknownMemberType]
            get_model(),
            graph=graph,
            exclude_types=_EXCLUDE_TYPES,
            cypher_prompt=_CYPHER_GENERATION_PROMPT,
            # Bắt buộc phải bật rõ ràng (an toàn mặc định của `langchain-neo4j` cho chain
            # tự sinh + tự chạy Cypher) — chấp nhận được vì `ReadOnlyNeo4jGraph` đã chặn
            # Cypher ghi, và graph chỉ chứa dữ liệu tham khảo tĩnh (PrimeKG), không PII.
            allow_dangerous_requests=True,
            top_k=10,
        )
    return _kg_chain


@tool
async def query_dermatology_kg(question: str) -> str:
    """Tra cứu knowledge graph da liễu (PrimeKG) để lấy thông tin CÓ CẤU TRÚC, đáng tin
    cậy hơn suy luận thuần của LLM: quan hệ bệnh-triệu chứng, bệnh-thuốc (chỉ định/chống
    chỉ định/off-label), bệnh liên quan hoặc dễ nhầm lẫn, bệnh-gen liên quan.

    Args:
        question: Câu hỏi tự nhiên, nên dùng tên bệnh/thuốc bằng tiếng Anh (dữ liệu gốc
            tiếng Anh) để khớp đúng thực thể, vd "What drugs are contraindicated for
            psoriasis?", "What symptoms are associated with pemphigus?".
    """
    chain = _get_chain()
    result = await chain.ainvoke({"query": question})
    return str(result.get("result") or "Không tìm thấy thông tin liên quan trong knowledge graph.")
