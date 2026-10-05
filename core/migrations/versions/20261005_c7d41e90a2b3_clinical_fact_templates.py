"""clinical fact templates — clinical_facts tham chiếu mẫu thay vì tự mang loại/nhãn/ontology

Revision ID: c7d41e90a2b3
Revises: 83942f933af4
Create Date: 2026-10-05 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c7d41e90a2b3'
down_revision: Union[str, Sequence[str], None] = '83942f933af4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('clinical_fact_templates',
    sa.Column('id', sa.String(length=64), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('fact_type', sa.String(length=32), nullable=False),
    sa.Column('label', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), server_default='', nullable=False),
    sa.Column('ontology_id', sa.String(length=128), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_clinical_fact_templates')),
    sa.UniqueConstraint('label', name=op.f('uq_clinical_fact_templates_label'))
    )
    # Giữ dữ liệu: mỗi (fact_type, label, ontology_id) đã có thành một mẫu rồi gắn fact vào mẫu đó
    op.add_column('clinical_facts', sa.Column('template_id', sa.String(length=64), nullable=True))
    op.execute("""
        INSERT INTO clinical_fact_templates (fact_type, label, ontology_id)
        SELECT DISTINCT ON (label) fact_type, label, ontology_id FROM clinical_facts ORDER BY label, created_at
    """)
    op.execute("""
        UPDATE clinical_facts f SET template_id = t.id
        FROM clinical_fact_templates t WHERE t.label = f.label
    """)
    op.alter_column('clinical_facts', 'template_id', nullable=False)
    op.create_foreign_key(op.f('fk_clinical_facts_template_id_clinical_fact_templates'), 'clinical_facts',
                          'clinical_fact_templates', ['template_id'], ['id'], ondelete='RESTRICT')
    op.create_index(op.f('ix_clinical_facts_template_id'), 'clinical_facts', ['template_id'], unique=False)
    op.drop_column('clinical_facts', 'fact_type')
    op.drop_column('clinical_facts', 'label')
    op.drop_column('clinical_facts', 'ontology_id')


def downgrade() -> None:
    op.add_column('clinical_facts', sa.Column('ontology_id', sa.String(length=128), nullable=True))
    op.add_column('clinical_facts', sa.Column('label', sa.String(length=255), nullable=True))
    op.add_column('clinical_facts', sa.Column('fact_type', sa.String(length=32), nullable=True))
    op.execute("""
        UPDATE clinical_facts f SET fact_type = t.fact_type, label = t.label, ontology_id = t.ontology_id
        FROM clinical_fact_templates t WHERE t.id = f.template_id
    """)
    op.alter_column('clinical_facts', 'label', nullable=False)
    op.alter_column('clinical_facts', 'fact_type', nullable=False)
    op.drop_index(op.f('ix_clinical_facts_template_id'), table_name='clinical_facts')
    op.drop_constraint(op.f('fk_clinical_facts_template_id_clinical_fact_templates'), 'clinical_facts', type_='foreignkey')
    op.drop_column('clinical_facts', 'template_id')
    op.drop_table('clinical_fact_templates')
