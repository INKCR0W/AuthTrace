"""initial schema

Revision ID: 20260501_0001
Revises:
Create Date: 2026-05-01 21:50:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260501_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "management_sources",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("source_key", sa.String(length=64), nullable=False),
        sa.Column("source_name", sa.String(length=128), nullable=False),
        sa.Column("base_url", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("source_key", name="uq_management_sources_source_key"),
    )

    op.create_table(
        "scan_jobs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("trigger_mode", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("scan_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scan_finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_accounts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("eligible_accounts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("scanned_accounts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_accounts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_accounts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_401_events", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_quota_events", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["source_id"], ["management_sources.id"], name="fk_scan_jobs_source_id"),
    )
    op.create_index("ix_scan_jobs_source_id_scan_started_at", "scan_jobs", ["source_id", "scan_started_at"])
    op.create_index("ix_scan_jobs_status_scan_started_at", "scan_jobs", ["status", "scan_started_at"])

    op.create_table(
        "accounts",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("auth_index", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("account", sa.String(length=255), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("account_type", sa.String(length=64), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("chatgpt_account_id", sa.String(length=128), nullable=True),
        sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("upstream_status", sa.String(length=64), nullable=True),
        sa.Column("status_message", sa.Text(), nullable=True),
        sa.Column("current_status_code", sa.Integer(), nullable=True),
        sa.Column("current_is_401", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("current_invalid_quota", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("current_weekly_used_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column("current_weekly_reset_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_short_used_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column("current_short_reset_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_remaining", sa.Numeric(12, 2), nullable=True),
        sa.Column("current_limit_reached", sa.Boolean(), nullable=True),
        sa.Column("current_allowed", sa.Boolean(), nullable=True),
        sa.Column("current_last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("source_deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "current_weekly_used_percent is null or current_weekly_used_percent between 0 and 100",
            name="current_weekly_pct",
        ),
        sa.CheckConstraint(
            "current_short_used_percent is null or current_short_used_percent between 0 and 100",
            name="current_short_pct",
        ),
        sa.ForeignKeyConstraint(["source_id"], ["management_sources.id"], name="fk_accounts_source_id"),
        sa.UniqueConstraint("source_id", "auth_index", name="uq_accounts_source_auth_index"),
    )
    op.create_index("ix_accounts_provider_account_type", "accounts", ["provider", "account_type"])
    op.create_index(
        "ix_accounts_current_is_401_current_last_checked_at",
        "accounts",
        ["current_is_401", "current_last_checked_at"],
    )
    op.create_index(
        "ix_accounts_current_invalid_quota_current_last_checked_at",
        "accounts",
        ["current_invalid_quota", "current_last_checked_at"],
    )
    op.create_index("ix_accounts_disabled_current_last_checked_at", "accounts", ["disabled", "current_last_checked_at"])
    op.create_index("ix_accounts_last_seen_at", "accounts", ["last_seen_at"])

    op.create_table(
        "account_snapshots",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("scan_job_id", sa.BigInteger(), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot_status", sa.String(length=32), nullable=False),
        sa.Column("probe_status_code", sa.Integer(), nullable=True),
        sa.Column("is_401", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("quota_status_code", sa.Integer(), nullable=True),
        sa.Column("invalid_quota", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("quota_source", sa.String(length=32), nullable=True),
        sa.Column("weekly_used_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column("weekly_reset_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("short_used_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column("short_reset_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("remaining", sa.Numeric(12, 2), nullable=True),
        sa.Column("limit_reached", sa.Boolean(), nullable=True),
        sa.Column("allowed", sa.Boolean(), nullable=True),
        sa.Column("status_message", sa.Text(), nullable=True),
        sa.Column("raw_auth_file_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("raw_usage_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "weekly_used_percent is null or weekly_used_percent between 0 and 100",
            name="weekly_pct",
        ),
        sa.CheckConstraint(
            "short_used_percent is null or short_used_percent between 0 and 100",
            name="short_pct",
        ),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], name="fk_account_snapshots_account_id"),
        sa.ForeignKeyConstraint(["scan_job_id"], ["scan_jobs.id"], name="fk_account_snapshots_scan_job_id"),
    )
    op.create_index("ix_account_snapshots_account_id_checked_at", "account_snapshots", ["account_id", "checked_at"])
    op.create_index("ix_account_snapshots_scan_job_id", "account_snapshots", ["scan_job_id"])
    op.create_index("ix_account_snapshots_checked_at", "account_snapshots", ["checked_at"])
    op.create_index(
        "ix_account_snapshots_checked_at_is_401_true",
        "account_snapshots",
        ["checked_at"],
        postgresql_where=sa.text("is_401 = true"),
    )
    op.create_index(
        "ix_account_snapshots_checked_at_invalid_quota_true",
        "account_snapshots",
        ["checked_at"],
        postgresql_where=sa.text("invalid_quota = true"),
    )

    op.create_table(
        "account_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("related_snapshot_id", sa.BigInteger(), nullable=False),
        sa.Column("previous_snapshot_id", sa.BigInteger(), nullable=True),
        sa.Column("from_status_code", sa.Integer(), nullable=True),
        sa.Column("to_status_code", sa.Integer(), nullable=True),
        sa.Column("from_is_401", sa.Boolean(), nullable=True),
        sa.Column("to_is_401", sa.Boolean(), nullable=True),
        sa.Column("from_invalid_quota", sa.Boolean(), nullable=True),
        sa.Column("to_invalid_quota", sa.Boolean(), nullable=True),
        sa.Column("from_disabled", sa.Boolean(), nullable=True),
        sa.Column("to_disabled", sa.Boolean(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], name="fk_account_events_account_id"),
        sa.ForeignKeyConstraint(
            ["related_snapshot_id"],
            ["account_snapshots.id"],
            name="fk_account_events_related_snapshot_id",
        ),
        sa.ForeignKeyConstraint(
            ["previous_snapshot_id"],
            ["account_snapshots.id"],
            name="fk_account_events_previous_snapshot_id",
        ),
        sa.UniqueConstraint("account_id", "event_type", "related_snapshot_id", name="uq_account_events_unique_transition"),
    )
    op.create_index("ix_account_events_account_id_event_time", "account_events", ["account_id", "event_time"])
    op.create_index("ix_account_events_event_type_event_time", "account_events", ["event_type", "event_time"])
    op.create_index("ix_account_events_related_snapshot_id", "account_events", ["related_snapshot_id"])


def downgrade() -> None:
    op.drop_index("ix_account_events_related_snapshot_id", table_name="account_events")
    op.drop_index("ix_account_events_event_type_event_time", table_name="account_events")
    op.drop_index("ix_account_events_account_id_event_time", table_name="account_events")
    op.drop_table("account_events")

    op.drop_index("ix_account_snapshots_checked_at_invalid_quota_true", table_name="account_snapshots")
    op.drop_index("ix_account_snapshots_checked_at_is_401_true", table_name="account_snapshots")
    op.drop_index("ix_account_snapshots_checked_at", table_name="account_snapshots")
    op.drop_index("ix_account_snapshots_scan_job_id", table_name="account_snapshots")
    op.drop_index("ix_account_snapshots_account_id_checked_at", table_name="account_snapshots")
    op.drop_table("account_snapshots")

    op.drop_index("ix_accounts_last_seen_at", table_name="accounts")
    op.drop_index("ix_accounts_disabled_current_last_checked_at", table_name="accounts")
    op.drop_index("ix_accounts_current_invalid_quota_current_last_checked_at", table_name="accounts")
    op.drop_index("ix_accounts_current_is_401_current_last_checked_at", table_name="accounts")
    op.drop_index("ix_accounts_provider_account_type", table_name="accounts")
    op.drop_table("accounts")

    op.drop_index("ix_scan_jobs_status_scan_started_at", table_name="scan_jobs")
    op.drop_index("ix_scan_jobs_source_id_scan_started_at", table_name="scan_jobs")
    op.drop_table("scan_jobs")

    op.drop_table("management_sources")
