"""Dữ liệu phụ của tin nhắn AI (`messages.metadata`, JSONB): các bước (`Step`), câu hỏi lại, nguồn trích dẫn. Không phải entity
nghiệp vụ — không có bảng riêng, chỉ được lưu nguyên khối trong JSON và truyền qua wire / agent — nên nằm ở `common`
thay vì `app/dto/base/`."""

from typing import Any, Literal

from pydantic import BaseModel, field_validator


class ChoiceOption(BaseModel):
    id: str
    label: str


class AnsweredChoice(BaseModel):
    option_id: str
    label: str
    custom: bool = False  # người dùng tự nhập thay vì chọn phương án có sẵn


class MessageChoice(BaseModel):
    question_id: str
    question: str
    options: list[ChoiceOption]
    answered: AnsweredChoice | None = None


class Step(BaseModel):
    """Một bước của AI trong một lượt trả lời: `default` (bước thường), `tool` (gọi tool, kể cả tool hỏi lại người dùng —
    khi đó có `choice`) hoặc `thinking` (tự suy nghĩ)."""

    id: str
    title: str
    content: str
    input: Any | None = None  # tham số tool, với bước gọi tool
    status: Literal["processing", "done"]
    type: Literal["default", "tool", "thinking"] = "default"
    choice: MessageChoice | None = None  # với bước tool hỏi lại người dùng (`ask_user`)

    @field_validator("type", mode="before")
    @classmethod
    def _legacy_tool_types(cls, v: object) -> object:
        # tin nhắn đã lưu trước khi gộp còn `tool_call` / `tool_ask` trong `messages.metadata`
        return "tool" if v in ("tool_call", "tool_ask") else v


class Source(BaseModel):
    """Một nguồn tri thức AI dùng làm căn cứ. `reference` là khoá trong kho tương ứng (id chunk Qdrant, id nút Neo4j, URL)."""

    kind: Literal["guideline", "document", "kg", "web"]
    title: str
    reference: str
    url: str | None = None
    content: str = ""  # đoạn trích
