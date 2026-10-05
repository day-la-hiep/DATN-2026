"""Bounded context Dữ kiện lâm sàng: mẫu fact chuẩn và fact trích từ hội thoại."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel

from app.common.constant import ClinicalFactType

if TYPE_CHECKING:
    from app.dto.base.conversation import Message


class ClinicalFactTemplate(BaseModel):
    """Mẫu dữ kiện lâm sàng trong danh mục chuẩn (ví dụ "ngứa", "dị ứng penicillin"). Agent chỉ được trích fact theo mẫu
    có sẵn để nhãn và `ontology_id` nhất quán giữa các bệnh nhân."""

    id: str
    fact_type: ClinicalFactType
    label: str
    description: str = ""  # gợi ý cho agent / bác sĩ biết cần hỏi và ghi gì vào `ClinicalFact.detail`
    ontology_id: str | None = None  # id DermO / PrimeKG đã chuẩn hoá — dùng để vẽ KG liên quan bệnh nhân


class ClinicalProvenance(BaseModel):
    """Nguồn gốc của một `ClinicalFact` (`ClinicalFact.provenances`): tin nhắn mà fact được trích ra, để bác sĩ truy ngược
    đúng tin gốc làm bằng chứng."""

    message: Message


class ClinicalFact(BaseModel):
    """Dữ kiện lâm sàng của một bệnh nhân, luôn được tạo từ một `ClinicalFactTemplate`. Không sửa đè: bệnh nhân đính chính
    thì tạo fact mới và đánh dấu fact cũ `superseded`, để bác sĩ vẫn thấy được lịch sử khai báo."""

    id: str
    template: ClinicalFactTemplate
    detail: str = ""  # giá trị cụ thể của bệnh nhân: vị trí, thời gian khởi phát, mức độ, diễn tiến...
    provenances: list[ClinicalProvenance] = []  # nguồn gốc của fact; mỗi nguồn chứa tin nhắn gốc
    status: Literal["active", "superseded"] = "active"
    superseded_by: ClinicalFact | None = None
    created_at: datetime | None = None
