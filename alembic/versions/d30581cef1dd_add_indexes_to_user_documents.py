"""add indexes to user_documents

Revision ID: xxxxx
Revises:
Create Date: 2025-12-28
"""
from alembic import op


# revision identifiers
revision = 'xxxxx'  # оставь как сгенерировано
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Создаём индексы для оптимизации запросов
    op.create_index(
        'idx_user_docs_user_type_deleted',
        'user_documents',
        ['user_id', 'file_type', 'is_deleted']
    )
    op.create_index(
        'idx_user_docs_user_type_status',
        'user_documents',
        ['user_id', 'file_type', 'status']
    )
    op.create_index(
        'idx_user_docs_upload_date',
        'user_documents',
        ['upload_date']
    )


def downgrade() -> None:
    # Откат - удаляем индексы
    op.drop_index('idx_user_docs_upload_date', table_name='user_documents')
    op.drop_index('idx_user_docs_user_type_status', table_name='user_documents')
    op.drop_index('idx_user_docs_user_type_deleted', table_name='user_documents')