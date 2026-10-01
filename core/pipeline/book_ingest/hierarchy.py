"""Cây mục lục: gán `parent_id` và `path` (từ gốc đến chính nó) cho các mục theo thứ tự đọc."""
from typing import Any


def build_tree(nodes: list[dict[str, Any]]) -> None:
    """Cha = mục có cấp thấp hơn gần nhất phía trên. Sửa tại chỗ."""
    stack: list[dict[str, Any]] = []
    for n in nodes:
        while stack and stack[-1]["level"] >= n["level"]:
            stack.pop()
        n["parent_id"] = stack[-1]["id"] if stack else None
        n["path"] = [x["title"] for x in stack] + [n["title"]]
        stack.append(n)
