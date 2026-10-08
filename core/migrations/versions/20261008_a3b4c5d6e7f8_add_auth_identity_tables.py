"""add auth identity tables

Revision ID: a3b4c5d6e7f8
Revises: 3e4b8f67b9ca
Create Date: 2026-10-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a3b4c5d6e7f8"
down_revision: Union[str, Sequence[str], None] = "3e4b8f67b9ca"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "doctors",
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_doctors_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_doctors")),
    )
    op.create_table(
        "admins",
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_admins_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_admins")),
    )
    op.create_table(
        "patient_profiles",
        sa.Column("id", sa.String(length=64), server_default=sa.text("gen_random_uuid()::text"), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("dob", sa.Date(), nullable=False),
        sa.Column("gender", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_patient_profiles_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_patient_profiles")),
    )
    op.create_index(
        op.f("ix_patient_profiles_user_id"), "patient_profiles", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_patient_profiles_user_id"), table_name="patient_profiles")
    op.drop_table("patient_profiles")
    op.drop_table("admins")
    op.drop_table("doctors")