"""Quản lý vòng đời các instance + provider DI"""

import threading
from collections.abc import AsyncGenerator, Callable
from typing import Annotated, Any, TypeVar

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.infra.docling_client import DoclingClient
from app.infra.embedding_client import EmbeddingClient
from app.infra.minio_client import MinioClient
from app.infra.neo4j_client import Neo4jClient
from app.infra.postgres_client import PostgresClient
from app.infra.qdrant_client import QdrantVectorClient
from app.infra.rabbitmq_client import RabbitMQClient
from app.infra.redis_client import RedisClient
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.file_repository import FileRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.patient_profile_repository import PatientProfileRepository
from app.services.file_store_service import FileStoreService
from app.repositories.document_repository import DocumentRepository
from app.services.document_service import DocumentService
from app.services.conversation_service import ConversationService
from app.services.knowledge_base_service import KnowledgeBaseService
from app.services.knowledge_graph_service import KnowledgeGraphService
from app.services.message_service import MessageService
from app.services.document_ingest_pipeline_service import DocumentIngestPipelineService

T = TypeVar("T")

# ---------------------------------------------------------------- registry instance (một mỗi process)
_instances: dict[str, Any] = {}
_guard = threading.RLock()


def _singleton(key: str, factory: Callable[[], T]) -> T:
    with _guard:
        if key not in _instances:
            _instances[key] = factory()
        return _instances[key]  # type: ignore[no-any-return]


def set_instance(key: str, instance: Any) -> None:
    """Test thay một instance (key = tên hàm `get_*` bỏ tiền tố `get_`, vd "redis_client")."""
    with _guard:
        _instances[key] = instance


def reset_instances() -> None:
    """Quên mọi instance (không đóng). Dùng trong test."""
    with _guard:
        _instances.clear()


async def close_clients() -> None:
    """Đóng mọi client đã tạo — gọi khi tắt Core/worker."""
    with _guard:
        items = list(_instances.values())
        _instances.clear()
    for obj in items:
        close = getattr(obj, "close", None)
        if close is None:
            continue
        result = close()
        if hasattr(result, "__await__"):
            await result


# ---------------------------------------------------------------- infra client
def get_postgres_client() -> PostgresClient:
    return _singleton("postgres_client", PostgresClient.from_settings)


def get_redis_client() -> RedisClient:
    return _singleton("redis_client", RedisClient.from_settings)


def get_rabbitmq_client() -> RabbitMQClient:
    return _singleton("rabbitmq_client", RabbitMQClient)


def get_qdrant_client() -> QdrantVectorClient:
    return _singleton("qdrant_client", QdrantVectorClient.from_settings)


def get_neo4j_client() -> Neo4jClient:
    return _singleton("neo4j_client", Neo4jClient.from_settings)


def get_minio_client() -> MinioClient:
    return _singleton("minio_client", MinioClient.from_settings)


def get_docling_client() -> DoclingClient:
    return _singleton("docling_client", DoclingClient)


def get_embedding_client() -> EmbeddingClient:
    return _singleton("embedding_client", EmbeddingClient)


# ---------------------------------------------------------------- service dùng chung
def get_knowledge_base_service() -> KnowledgeBaseService:
    return _singleton(
        "knowledge_base_service",
        lambda: KnowledgeBaseService(get_qdrant_client()),
    )


def get_knowledge_graph_service() -> KnowledgeGraphService:
    return _singleton(
        "knowledge_graph_service",
        lambda: KnowledgeGraphService(get_neo4j_client()),
    )


def get_file_store_service() -> FileStoreService:
    """Kho file của bucket ảnh đính kèm tin nhắn."""
    return _singleton("file_store_service", lambda: FileStoreService(get_minio_client(), settings.MINIO_BUCKET))


def get_document_file_store() -> FileStoreService:
    """Kho file của bucket tài liệu (pipeline `document_ingest`)."""
    return _singleton("document_file_store", lambda: FileStoreService(get_minio_client(), settings.MINIO_DOCUMENTS_BUCKET))


def get_document_repository() -> DocumentRepository:
    return _singleton("document_repository", lambda: DocumentRepository(get_document_file_store(), get_postgres_client().sync_session_factory))


def get_document_service() -> DocumentService:
    return _singleton(
        "document_service",
        lambda: DocumentService(
            get_document_repository(),
            get_qdrant_client(),
            settings.QDRANT_DOCUMENT_COLLECTION,
        ),
    )


def get_document_ingest_pipeline_service() -> DocumentIngestPipelineService:
    return _singleton(
        "document_ingest_pipeline_service",
        lambda: DocumentIngestPipelineService(
            get_document_service(),
            get_document_repository(),
            docling=get_docling_client(),
            embedding=get_embedding_client(),
            rabbitmq=get_rabbitmq_client(),
            redis=get_redis_client(),
        ),
    )


# ---------------------------------------------------------------- theo request
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with get_postgres_client().session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_conversation_repository(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ConversationRepository:
    return ConversationRepository(db)


def get_patient_profile_repository(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PatientProfileRepository:
    return PatientProfileRepository(db)


def get_message_repository(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageRepository:
    return MessageRepository(db)


def get_file_repository(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FileRepository:
    return FileRepository(db)


def get_message_service(
    message_repository: Annotated[
        MessageRepository, Depends(get_message_repository)
    ],
    conversation_repository: Annotated[
        ConversationRepository, Depends(get_conversation_repository)
    ],
    file_repository: Annotated[FileRepository, Depends(get_file_repository)],
    redis: Annotated[RedisClient, Depends(get_redis_client)],
) -> MessageService:
    return MessageService(
        message_repository, conversation_repository, file_repository, get_file_store_service(), redis
    )


def get_conversation_service(
    conversation_repository: Annotated[
        ConversationRepository, Depends(get_conversation_repository)
    ],
    patient_profile_repository: Annotated[
        PatientProfileRepository, Depends(get_patient_profile_repository)
    ],
    message_service: Annotated[MessageService, Depends(get_message_service)],
) -> ConversationService:
    return ConversationService(conversation_repository, patient_profile_repository, message_service)
