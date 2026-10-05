"""đổi tên clinical_fact_sources -> clinical_provenances cho khớp entity `ClinicalProvenance`

Revision ID: d8e52f01b3c4
Revises: c7d41e90a2b3
Create Date: 2026-10-05 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'd8e52f01b3c4'
down_revision: Union[str, Sequence[str], None] = 'c7d41e90a2b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (tên cũ, tên mới) — đổi cả constraint để khớp naming convention của metadata, tránh autogenerate sinh diff thừa
_CONSTRAINTS = [
    ('pk_clinical_fact_sources', 'pk_clinical_provenances'),
    ('fk_clinical_fact_sources_fact_id_clinical_facts', 'fk_clinical_provenances_fact_id_clinical_facts'),
    ('fk_clinical_fact_sources_message_id_messages', 'fk_clinical_provenances_message_id_messages'),
]


def upgrade() -> None:
    op.rename_table('clinical_fact_sources', 'clinical_provenances')
    for old, new in _CONSTRAINTS:
        op.execute(f'ALTER TABLE clinical_provenances RENAME CONSTRAINT {old} TO {new}')


def downgrade() -> None:
    for old, new in _CONSTRAINTS:
        op.execute(f'ALTER TABLE clinical_provenances RENAME CONSTRAINT {new} TO {old}')
    op.rename_table('clinical_provenances', 'clinical_fact_sources')
