"""Neo4j dùng chung (PrimeKG + DermO): kết nối async lười + chạy Cypher, trả danh sách dict. Truy vấn cụ thể nằm ở service
(`KnowledgeGraphService`). Instance do `app/api/deps.py` tạo và đóng."""
from typing import Any, LiteralString

from neo4j import AsyncDriver, AsyncGraphDatabase

from app.config.settings import settings


class Neo4jClient:
    def __init__(self, url: str, user: str, password: str) -> None:
        self._url, self._auth = url, (user, password)
        self._driver: AsyncDriver | None = None

    @classmethod
    def from_settings(cls) -> "Neo4jClient":
        return cls(settings.NEO4J_URL, settings.NEO4J_USER, settings.NEO4J_PASSWORD)

    @property
    def driver(self) -> AsyncDriver:
        if self._driver is None:
            self._driver = AsyncGraphDatabase.driver(self._url, auth=self._auth)  # pyright: ignore[reportUnknownMemberType]
        return self._driver

    async def run(self, query: LiteralString, **params: Any) -> list[dict[str, Any]]:
        async with self.driver.session() as session:  # pyright: ignore[reportUnknownMemberType]
            result = await session.run(query, **params)
            return [r.data() async for r in result]

    async def close(self) -> None:
        if self._driver is not None:
            await self._driver.close()
            self._driver = None
