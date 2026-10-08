"""set users id server default

Revision ID: c4d5e6f7a8b9
Revises: a3b4c5d6e7f8
Create Date: 2026-10-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, Sequence[str], None] = "a3b4c5d6e7f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "users",
        "id",
        server_default=sa.text("gen_random_uuid()::text"),
    )


def downgrade() -> None:
    op.alter_column("users", "id", server_default=None)