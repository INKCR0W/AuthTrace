from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.account import Account


@dataclass(slots=True)
class AuthFileSyncStats:
    total_accounts: int
    synced_accounts: int
    eligible_accounts: int
    missing_auth_index_accounts: int

    @property
    def skipped_accounts(self) -> int:
        return self.total_accounts - self.synced_accounts


def sync_accounts_from_auth_files(
    db: Session,
    *,
    source_id: int,
    auth_files: list[dict[str, Any]],
    seen_at: datetime,
    settings: Settings,
) -> AuthFileSyncStats:
    existing_accounts = db.scalars(select(Account).where(Account.source_id == source_id)).all()
    existing_by_auth_index = {account.auth_index: account for account in existing_accounts}

    incoming_auth_indices: set[str] = set()
    synced_accounts = 0
    eligible_accounts = 0
    missing_auth_index_accounts = 0

    for item in auth_files:
        auth_index = _normalize_optional_text(item.get("auth_index"))
        if auth_index is None:
            missing_auth_index_accounts += 1
            continue

        if _is_eligible_auth_file(item, settings):
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
        synced_accounts += 1

    for account in existing_accounts:
        if account.auth_index not in incoming_auth_indices:
            account.source_deleted_at = seen_at

    db.flush()
    return AuthFileSyncStats(
        total_accounts=len(auth_files),
        synced_accounts=synced_accounts,
        eligible_accounts=eligible_accounts,
        missing_auth_index_accounts=missing_auth_index_accounts,
    )


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
