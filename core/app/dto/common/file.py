from app.dto.base import File


class FileDto(File):
    """File trên wire"""

    url: str | None = None
