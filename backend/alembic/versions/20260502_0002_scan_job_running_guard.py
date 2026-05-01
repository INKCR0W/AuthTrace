"""add running scan job guard

Revision ID: 20260502_0002
Revises: 20260501_0001
Create Date: 2026-05-02 11:20:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260502_0002"
down_revision = "20260501_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    dialect_name = op.get_bind().dialect.name
    kwargs: dict[str, sa.TextClause] = {}
    if dialect_name == "postgresql":
        kwargs["postgresql_where"] = sa.text("status = 'running'")
    elif dialect_name == "sqlite":
        kwargs["sqlite_where"] = sa.text("status = 'running'")

    op.create_index(
        "uq_scan_jobs_source_id_running",
        "scan_jobs",
        ["source_id"],
        unique=True,
        **kwargs,
    )


def downgrade() -> None:
    op.drop_index("uq_scan_jobs_source_id_running", table_name="scan_jobs")
