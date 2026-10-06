"""video_calls thuộc phiên tư vấn (consultation_session_id)

Revision ID: 3e4b8f67b9ca
Revises: 2d3a7e56a8b9
Create Date: 2026-10-06 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '3e4b8f67b9ca'
down_revision: Union[str, Sequence[str], None] = '2d3a7e56a8b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('video_calls', sa.Column('consultation_session_id', sa.String(length=64), nullable=True))
    # Giữ dữ liệu: gắn cuộc gọi cũ vào phiên gần nhất của hội thoại chứa tin cuộc gọi, tính tới lúc tin được tạo.
    # Cuộc gọi không khớp được phiên nào sẽ làm bước NOT NULL bên dưới báo lỗi, thay vì bị xoá âm thầm.
    op.execute("""
        UPDATE video_calls v SET consultation_session_id = (
            SELECT cs.id FROM messages m
            JOIN consultation_sessions cs ON cs.conversation_id = m.conversation_id AND cs.requested_at <= m.created_at
            WHERE m.video_call_id = v.id
            ORDER BY cs.requested_at DESC LIMIT 1)
    """)
    op.alter_column('video_calls', 'consultation_session_id', nullable=False)
    op.create_foreign_key(op.f('fk_video_calls_consultation_session_id_consultation_sessions'), 'video_calls',
                          'consultation_sessions', ['consultation_session_id'], ['id'], ondelete='CASCADE')
    op.create_index(op.f('ix_video_calls_consultation_session_id'), 'video_calls', ['consultation_session_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_video_calls_consultation_session_id'), table_name='video_calls')
    op.drop_constraint(op.f('fk_video_calls_consultation_session_id_consultation_sessions'), 'video_calls', type_='foreignkey')
    op.drop_column('video_calls', 'consultation_session_id')
