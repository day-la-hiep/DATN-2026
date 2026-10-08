"""document_stages có khoá id riêng; document_overrides trỏ document_stage_id (bỏ document_id, stage_id)

Revision ID: 0b185c34e6f7
Revises: fa074b23d5e6
Create Date: 2026-10-05 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0b185c34e6f7'
down_revision: Union[str, Sequence[str], None] = 'fa074b23d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # document_stages: thêm id (Postgres tự điền uuid cho dòng cũ), đổi PK kép thành id + unique(document_id, stage_id)
    op.add_column('document_stages', sa.Column(
        'id', sa.String(length=64), server_default=sa.text('gen_random_uuid()'), nullable=False))
    # override: thêm cột mới, nối tới bước theo (document_id, stage_id) cũ, rồi mới bỏ FK/PK/cột cũ để giữ dữ liệu
    op.add_column('document_overrides', sa.Column('document_stage_id', sa.String(length=64), nullable=True))
    op.drop_constraint(op.f('fk_document_overrides_document_id_document_stages'), 'document_overrides', type_='foreignkey')
    op.drop_constraint(op.f('pk_document_stages'), 'document_stages', type_='primary')
    op.create_primary_key(op.f('pk_document_stages'), 'document_stages', ['id'])
    op.create_unique_constraint(op.f('uq_document_stages_document_id'), 'document_stages', ['document_id', 'stage_id'])
    op.execute("""
        UPDATE document_overrides o SET document_stage_id = s.id
        FROM document_stages s WHERE s.document_id = o.document_id AND s.stage_id = o.stage_id
    """)
    op.drop_constraint(op.f('pk_document_overrides'), 'document_overrides', type_='primary')
    op.drop_column('document_overrides', 'document_id')
    op.drop_column('document_overrides', 'stage_id')
    op.alter_column('document_overrides', 'document_stage_id', nullable=False)
    op.create_primary_key(op.f('pk_document_overrides'), 'document_overrides', ['document_stage_id'])
    op.create_foreign_key(
        op.f('fk_document_overrides_document_stage_id_document_stages'), 'document_overrides', 'document_stages',
        ['document_stage_id'], ['id'], ondelete='CASCADE',
    )


def downgrade() -> None:
    op.add_column('document_overrides', sa.Column('document_id', sa.String(length=64), nullable=True))
    op.add_column('document_overrides', sa.Column('stage_id', sa.String(length=32), nullable=True))
    op.execute("""
        UPDATE document_overrides o SET document_id = s.document_id, stage_id = s.stage_id
        FROM document_stages s WHERE s.id = o.document_stage_id
    """)
    op.drop_constraint(op.f('fk_document_overrides_document_stage_id_document_stages'), 'document_overrides', type_='foreignkey')
    op.drop_constraint(op.f('pk_document_overrides'), 'document_overrides', type_='primary')
    op.drop_column('document_overrides', 'document_stage_id')
    op.alter_column('document_overrides', 'document_id', nullable=False)
    op.alter_column('document_overrides', 'stage_id', nullable=False)
    op.create_primary_key(op.f('pk_document_overrides'), 'document_overrides', ['document_id', 'stage_id'])
    op.drop_constraint(op.f('uq_document_stages_document_id'), 'document_stages', type_='unique')
    op.drop_constraint(op.f('pk_document_stages'), 'document_stages', type_='primary')
    op.create_primary_key(op.f('pk_document_stages'), 'document_stages', ['document_id', 'stage_id'])
    op.drop_column('document_stages', 'id')
    op.create_foreign_key(
        op.f('fk_document_overrides_document_id_document_stages'), 'document_overrides', 'document_stages',
        ['document_id', 'stage_id'], ['document_id', 'stage_id'], ondelete='CASCADE',
    )
