from app.dto.base import File


class FileDto(File):
    """File trên wire — kế thừa `app/dto/base/shared.py::File` nên field khớp base. `url` là field riêng của API: link
    presigned để FE xem trước, sinh lúc upload, không lưu trong base."""

    url: str | None = None
