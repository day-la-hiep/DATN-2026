"""Truy vấn DB cho `File` và bảng nối `message_files` (tệp đính kèm tin nhắn)."""
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.file import File
from app.models.message_file import MessageFile


class FileRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(self, file: File) -> File:
        self._db.add(file)
        await self._db.flush()
        return file

    async def by_storage_keys(self, keys: list[str]) -> dict[str, File]:
        rows = await self._db.scalars(select(File).where(File.storage_key.in_(keys)))
        return {f.storage_key: f for f in rows}

    async def attach_to_message(self, message_id: str, files: list[File]) -> None:
        self._db.add_all(MessageFile(message_id=message_id, file_id=f.id) for f in files)
        await self._db.flush()

    async def for_messages(self, message_ids: list[str]) -> dict[str, list[File]]:
        """Tệp đính kèm của nhiều tin trong 1 truy vấn (dựng danh sách tin không phải N+1)."""
        out: dict[str, list[File]] = defaultdict(list)
        if not message_ids:
            return out
        stmt = (
            select(MessageFile.message_id, File)
            .join(File, File.id == MessageFile.file_id)
            .where(MessageFile.message_id.in_(message_ids))
            .order_by(File.created_at)
        )
        for message_id, file in (await self._db.execute(stmt)).all():
            out[message_id].append(file)
        return out
