"""enforce one active processing job per document

Revision ID: 20260825_01
Revises: 20260819_01
Create Date: 2026-08-25
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260825_01"
down_revision: str | None = "20260819_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_processing_jobs_active_document",
        "processing_jobs",
        ["document_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('QUEUED', 'STARTED')"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_processing_jobs_active_document",
        table_name="processing_jobs",
    )
