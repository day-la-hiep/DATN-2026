"""State của chat graph (`agent/graph/chat_graph.py`): chỉ `messages` — chung kênh với graph tiền chẩn đoán nên lịch sử hội thoại
chỉ có một bản — và `route` là quyết định của bước lọc intent trong turn hiện tại."""
from typing import Annotated, Literal, NotRequired, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class ChatState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    route: NotRequired[Literal["answer", "diagnose"]]
