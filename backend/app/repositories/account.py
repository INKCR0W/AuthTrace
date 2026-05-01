from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.account import Account


@dataclass(slots=True)
class SyncedAuthFile:
    account: Account
    auth_file: dict[str, Any]
    eligible: bool


@dataclass(slots=True)
class AuthFileSyncResult:
    total_accounts: int
    synced_accounts: int
    eligible_accounts: int
    missing_auth_index_accounts: int
    synced_auth_files: list[SyncedAuthFile]

    @property
    def skipped_accounts(self) -> int:
        return self.total_accounts - self.synced_accounts

    @property
    def eligible_auth_files(self) -> list[SyncedAuthFile]:
        return [item for item in self.synced_auth_files if item.eligible]


@dataclass(slots=True)
class AccountListFilters:
    provider: str | None = None
    account_type: str | None = None
    current_is_401: bool | None = None
    current_invalid_quota: bool | None = None
    disabled: bool | None = None
    include_deleted: bool = False
    last_checked_from: datetime | None = None
    last_checked_to: datetime | None = None
    limit: int = 50
    offset: int = 0


def list_accounts(
    db: Session,
    *,
    filters: AccountListFilters,
) -> tuple[list[Account], int]:
    filtered_statement = _apply_account_filters(select(Account), filters=filters)
    filtered_count_statement = _apply_account_filters(select(func.count(Account.id)), filters=filters)

    items = list(
        db.scalars(
            filtered_statement.order_by(Account.current_last_checked_at.desc(), Account.id.desc())
            .offset(filters.offset)
            .limit(filters.limit)
        ).all()
    )
    total = int(db.scalar(filtered_count_statement) or 0)
    return items, total


def sync_accounts_from_auth_files(
    db: Session,
    *,
    source_id: int,
    auth_files: list[dict[str, Any]],
    seen_at: datetime,
    settings: Settings,
) -> AuthFileSyncResult:
    existing_accounts = db.scalars(select(Account).where(Account.source_id == source_id)).all()
    existing_by_auth_index = {account.auth_index: account for account in existing_accounts}

    incoming_auth_indices: set[str] = set()
    synced_accounts = 0
    eligible_accounts = 0
    missing_auth_index_accounts = 0
    synced_auth_files: list[SyncedAuthFile] = []

    for item in auth_files:
        auth_index = _normalize_optional_text(item.get("auth_index"))
        if auth_index is None:
            missing_auth_index_accounts += 1
            continue

        is_eligible = _is_eligible_auth_file(item, settings)
        if is_eligible:
            eligible_accounts += 1

        incoming_auth_indices.add(auth_index)
        account = existing_by_auth_index.get(auth_index)
        if account is None:
            account = Account(
                source_id=source_id,
                auth_index=auth_index,
                name=_normalize_optional_text(item.get("name")) or auth_index,
                first_seen_at=seen_at,
                last_seen_at=seen_at,
            )
            db.add(account)
            existing_by_auth_index[auth_index] = account

        account.name = _normalize_optional_text(item.get("name")) or auth_index
        account.account = _normalize_optional_text(item.get("account"))
        account.email = _normalize_optional_text(item.get("email"))
        account.account_type = _extract_item_type(item)
        account.provider = _normalize_optional_text(item.get("provider"))
        account.chatgpt_account_id = _extract_chatgpt_account_id(item)
        account.disabled = bool(item.get("disabled"))
        account.upstream_status = _normalize_optional_text(item.get("status"))
        account.status_message = _stringify_text_value(item.get("status_message"))
        account.last_seen_at = seen_at
        account.source_deleted_at = None
        synced_auth_files.append(SyncedAuthFile(account=account, auth_file=item, eligible=is_eligible))
        synced_accounts += 1

    for account in existing_accounts:
        if account.auth_index not in incoming_auth_indices:
            account.source_deleted_at = seen_at

    db.flush()
    return AuthFileSyncResult(
        total_accounts=len(auth_files),
        synced_accounts=synced_accounts,
        eligible_accounts=eligible_accounts,
        missing_auth_index_accounts=missing_auth_index_accounts,
        synced_auth_files=synced_auth_files,
    )


def _apply_account_filters(statement: Select, *, filters: AccountListFilters) -> Select:
    if filters.provider:
        statement = statement.where(Account.provider == filters.provider)
    if filters.account_type:
        statement = statement.where(Account.account_type == filters.account_type)
    if filters.current_is_401 is not None:
        statement = statement.where(Account.current_is_401 == filters.current_is_401)
    if filters.current_invalid_quota is not None:
        statement = statement.where(Account.current_invalid_quota == filters.current_invalid_quota)
    if filters.disabled is not None:
        statement = statement.where(Account.disabled == filters.disabled)
    if not filters.include_deleted:
        statement = statement.where(Account.source_deleted_at.is_(None))
    if filters.last_checked_from is not None:
        statement = statement.where(Account.current_last_checked_at >= filters.last_checked_from)
    if filters.last_checked_to is not None:
        statement = statement.where(Account.current_last_checked_at <= filters.last_checked_to)
    return statement


def _extract_item_type(item: dict[str, Any]) -> str | None:
    return _normalize_optional_text(item.get("type")) or _normalize_optional_text(item.get("typo"))


def _extract_chatgpt_account_id(item: dict[str, Any]) -> str | None:
    for key in ("chatgpt_account_id", "chatgptAccountId", "account_id", "accountId"):
        value = _normalize_optional_text(item.get(key))
        if value is not None:
            return value
    return None


def _is_eligible_auth_file(item: dict[str, Any], settings: Settings) -> bool:
    if bool(item.get("disabled")):
        return False
    if bool(item.get("standby")):
        return False
    if _normalize_optional_text(item.get("auth_index")) is None:
        return False

    status = (_normalize_optional_text(item.get("status")) or "unknown").lower()
    if status not in {"active", "unknown", "error"}:
        return False

    item_type = (_extract_item_type(item) or "").lower()
    provider = (_normalize_optional_text(item.get("provider")) or "").lower()
    target_type = (settings.management_target_type or "").lower()
    target_provider = (settings.management_provider or "").lower()

    if target_type and item_type != target_type:
        return False
    if target_provider and provider != target_provider:
        return False

    return True


def _normalize_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _stringify_text_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    return json.dumps(value, ensure_ascii=False)
