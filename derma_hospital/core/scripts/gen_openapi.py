"""Sinh `docs/openapi.yaml` từ chính FastAPI app (`main.app.openapi()`) — single
source of truth là code (`app/api/*.py`, `app/dto/*.py`), không viết tay YAML.

Chạy:  cd core && python scripts/gen_openapi.py
"""
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main  # noqa: E402

HEADER = (
    "# Sinh tự động từ FastAPI app (main.app.openapi()) — KHÔNG sửa tay.\n"
    "# Regenerate: cd core && python scripts/gen_openapi.py\n"
    "# Nguồn: app/api/conversation_api.py, app/api/health.py, app/dto/*.\n"
    "# SSE (/conversations/{conversationId}/stream) KHÔNG có ở đây — xem docs/asyncapi.yaml.\n"
)

OUT_PATH = Path(__file__).resolve().parent.parent / "docs" / "openapi.yaml"


def main_() -> None:
    schema = main.app.openapi()
    with OUT_PATH.open("w", encoding="utf-8") as f:
        f.write(HEADER)
        yaml.dump(schema, f, sort_keys=False, allow_unicode=True, width=100)
    print(f"Đã ghi {OUT_PATH} ({len(schema['paths'])} path).")


if __name__ == "__main__":
    main_()
