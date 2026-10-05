"""clinical_facts thuộc hồ sơ bệnh nhân (patient_profile_id) thay vì hội thoại

Revision ID: e9f63a12c4d5
Revises: d8e52f01b3c4
Create Date: 2026-10-05 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'e9f63a12c4d5'
down_revision: Union[str, Sequence[str], None] = 'd8e52f01b3c4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Giữ dữ liệu: suy hồ sơ bệnh nhân từ hội thoại cũ của fact rồi mới bỏ cột
    op.add_column('clinical_facts', sa.Column('patient_profile_id', sa.String(length=64), nullable=True))
    op.execute("""
        UPDATE clinical_facts f SET patient_profile_id = c.patient_profile_id
        FROM conversations c WHERE c.id = f.conversation_id
    """)
    op.alter_column('clinical_facts', 'patient_profile_id', nullable=False)
    op.create_foreign_key(op.f('fk_clinical_facts_patient_profile_id_patient_profiles'), 'clinical_facts',
                          'patient_profiles', ['patient_profile_id'], ['id'], ondelete='CASCADE')
    op.create_index(op.f('ix_clinical_facts_patient_profile_id'), 'clinical_facts', ['patient_profile_id'], unique=False)
    op.drop_index(op.f('ix_clinical_facts_conversation_id'), table_name='clinical_facts')
    op.drop_constraint(op.f('fk_clinical_facts_conversation_id_conversations'), 'clinical_facts', type_='foreignkey')
    op.drop_column('clinical_facts', 'conversation_id')


def downgrade() -> None:
    # Không thể khôi phục hội thoại gốc của fact (một fact giờ có thể đến từ nhiều hội thoại): lấy hội thoại mới nhất
    # của hồ sơ; fact của hồ sơ chưa có hội thoại nào sẽ bị xoá vì cột cũ NOT NULL
    op.add_column('clinical_facts', sa.Column('conversation_id', sa.String(length=64), nullable=True))
    op.execute("""
        UPDATE clinical_facts f SET conversation_id = (
            SELECT c.id FROM conversations c WHERE c.patient_profile_id = f.patient_profile_id
            ORDER BY c.created_at DESC LIMIT 1)
    """)
    op.execute("DELETE FROM clinical_facts WHERE conversation_id IS NULL")
    op.alter_column('clinical_facts', 'conversation_id', nullable=False)
    op.create_foreign_key(op.f('fk_clinical_facts_conversation_id_conversations'), 'clinical_facts',
                          'conversations', ['conversation_id'], ['id'], ondelete='CASCADE')
    op.create_index(op.f('ix_clinical_facts_conversation_id'), 'clinical_facts', ['conversation_id'], unique=False)
    op.drop_index(op.f('ix_clinical_facts_patient_profile_id'), table_name='clinical_facts')
    op.drop_constraint(op.f('fk_clinical_facts_patient_profile_id_patient_profiles'), 'clinical_facts', type_='foreignkey')
    op.drop_column('clinical_facts', 'patient_profile_id')
