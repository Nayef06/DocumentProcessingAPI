"""add text chunk full-text search index

Revision ID: 20260819_01
Revises:
Create Date: 2026-08-19
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260819_01"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_text_chunks_content_fts",
        "text_chunks",
        [sa.text("to_tsvector('english', content)")],
        unique=False,
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_text_chunks_content_fts", table_name="text_chunks")
