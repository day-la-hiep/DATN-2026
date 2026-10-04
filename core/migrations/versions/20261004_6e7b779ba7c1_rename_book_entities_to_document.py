"""rename book entities to document

Revision ID: 6e7b779ba7c1
Revises: 251c35026329
Create Date: 2026-10-04 08:50:50.990032

Đổi tên bảng/cột Book* -> Document* theo entity nghiệp vụ mới (`app/dto/base/document.py`).
Dùng `rename_table`/`alter_column` (không drop/create) để giữ dữ liệu sách đã nhập trong lúc
phát triển pipeline — autogenerate mặc định sinh drop+create (mất dữ liệu), đã sửa tay lại đây.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '6e7b779ba7c1'
down_revision: Union[str, Sequence[str], None] = '251c35026329'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.rename_table('books', 'documents')
    op.execute("ALTER TABLE documents RENAME CONSTRAINT pk_books TO pk_documents")

    op.rename_table('book_stages', 'document_stages')
    op.alter_column('document_stages', 'book_id', new_column_name='document_id')
    op.execute(
        "ALTER TABLE document_stages RENAME CONSTRAINT pk_book_stages TO pk_document_stages"
    )
    op.execute(
        "ALTER TABLE document_stages RENAME CONSTRAINT fk_book_stages_book_id_books TO fk_document_stages_document_id_documents"
    )

    op.rename_table('book_overrides', 'document_overrides')
    op.alter_column('document_overrides', 'book_id', new_column_name='document_id')
    op.execute(
        "ALTER TABLE document_overrides RENAME CONSTRAINT pk_book_overrides TO pk_document_overrides"
    )
    op.execute(
        "ALTER TABLE document_overrides RENAME CONSTRAINT fk_book_overrides_book_id_books TO fk_document_overrides_document_id_documents"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE document_overrides RENAME CONSTRAINT fk_document_overrides_document_id_documents TO fk_book_overrides_book_id_books"
    )
    op.execute(
        "ALTER TABLE document_overrides RENAME CONSTRAINT pk_document_overrides TO pk_book_overrides"
    )
    op.alter_column('document_overrides', 'document_id', new_column_name='book_id')
    op.rename_table('document_overrides', 'book_overrides')

    op.execute(
        "ALTER TABLE document_stages RENAME CONSTRAINT fk_document_stages_document_id_documents TO fk_book_stages_book_id_books"
    )
    op.execute(
        "ALTER TABLE document_stages RENAME CONSTRAINT pk_document_stages TO pk_book_stages"
    )
    op.alter_column('document_stages', 'document_id', new_column_name='book_id')
    op.rename_table('document_stages', 'book_stages')

    op.execute("ALTER TABLE documents RENAME CONSTRAINT pk_documents TO pk_books")
    op.rename_table('documents', 'books')
