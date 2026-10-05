"""pre_consultation_reports chỉ giữ summary: bỏ hypotheses, sources và bảng nối pre_consultation_report_facts

Revision ID: 1c296d45f7a8
Revises: 0b185c34e6f7
Create Date: 2026-10-05 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '1c296d45f7a8'
down_revision: Union[str, Sequence[str], None] = '0b185c34e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Chưa có code nào ghi các bảng/cột này, bỏ thẳng không mất dữ liệu nhập
    op.drop_table('pre_consultation_report_facts')
    op.drop_column('pre_consultation_reports', 'hypotheses')
    op.drop_column('pre_consultation_reports', 'sources')


def downgrade() -> None:
    op.add_column('pre_consultation_reports', sa.Column(
        'sources', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False))
    op.add_column('pre_consultation_reports', sa.Column(
        'hypotheses', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False))
    op.create_table('pre_consultation_report_facts',
    sa.Column('report_id', sa.String(length=64), nullable=False),
    sa.Column('fact_id', sa.String(length=64), nullable=False),
    sa.ForeignKeyConstraint(['fact_id'], ['clinical_facts.id'], name=op.f('fk_pre_consultation_report_facts_fact_id_clinical_facts'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['report_id'], ['pre_consultation_reports.id'], name=op.f('fk_pre_consultation_report_facts_report_id_pre_consultation_reports'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('report_id', 'fact_id', name=op.f('pk_pre_consultation_report_facts'))
    )
