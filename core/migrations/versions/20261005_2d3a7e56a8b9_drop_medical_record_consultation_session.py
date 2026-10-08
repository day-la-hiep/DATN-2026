"""medical_records bỏ consultation_session_id — bệnh án không gắn với phiên tư vấn

Revision ID: 2d3a7e56a8b9
Revises: 1c296d45f7a8
Create Date: 2026-10-05 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '2d3a7e56a8b9'
down_revision: Union[str, Sequence[str], None] = '1c296d45f7a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Chưa có code nào ghi cột này nên bỏ thẳng không mất dữ liệu nhập
    op.drop_constraint(op.f('fk_medical_records_consultation_session_id_consultation_sessions'), 'medical_records', type_='foreignkey')
    op.drop_column('medical_records', 'consultation_session_id')


def downgrade() -> None:
    op.add_column('medical_records', sa.Column('consultation_session_id', sa.String(length=64), nullable=True))
    op.create_foreign_key(op.f('fk_medical_records_consultation_session_id_consultation_sessions'), 'medical_records',
                          'consultation_sessions', ['consultation_session_id'], ['id'], ondelete='SET NULL')
