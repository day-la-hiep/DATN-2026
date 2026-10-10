"""add auth identity tables (rỗng)

Revision ID: a3b4c5d6e7f8
Revises: 3e4b8f67b9ca
Create Date: 2026-10-08

"""
from typing import Sequence, Union


revision: str = "a3b4c5d6e7f8"
down_revision: Union[str, Sequence[str], None] = "3e4b8f67b9ca"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # `doctors`, `admins`, `patient_profiles` đã do 7a1c2d3e4f50 tạo; bản gốc tạo trùng nên lỗi DuplicateTable.
    # Giữ revision rỗng để DB đã stamp revision này vẫn khớp chuỗi.
    pass


def downgrade() -> None:
    pass
