"""document_overrides trỏ FK kép tới document_stages thay vì documents

Revision ID: fa074b23d5e6
Revises: e9f63a12c4d5
Create Date: 2026-10-05 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'fa074b23d5e6'
down_revision: Union[str, Sequence[str], None] = 'e9f63a12c4d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Giữ override cũ: bổ sung dòng bước còn thiếu để FK mới không bị vi phạm
    op.execute("""
        INSERT INTO document_stages (document_id, stage_id, state)
        SELECT o.document_id, o.stage_id, 'not_started' FROM document_overrides o
        WHERE NOT EXISTS (
            SELECT 1 FROM document_stages s WHERE s.document_id = o.document_id AND s.stage_id = o.stage_id)
    """)
    op.drop_constraint(op.f('fk_document_overrides_document_id_documents'), 'document_overrides', type_='foreignkey')
    op.create_foreign_key(
        op.f('fk_document_overrides_document_id_document_stages'), 'document_overrides', 'document_stages',
        ['document_id', 'stage_id'], ['document_id', 'stage_id'], ondelete='CASCADE',
    )


def downgrade() -> None:
    op.drop_constraint(op.f('fk_document_overrides_document_id_document_stages'), 'document_overrides', type_='foreignkey')
    op.create_foreign_key(
        op.f('fk_document_overrides_document_id_documents'), 'document_overrides', 'documents',
        ['document_id'], ['id'], ondelete='CASCADE',
    )
