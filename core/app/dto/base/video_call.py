from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class VideoCall(BaseModel):
    room_id: str
    status: Literal["pending", "ongoing", "ended"]
    started_at: datetime | None = None
    ended_at: datetime | None = None
