from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any


LIMIT_KEYWORDS = (
    "usage_limit_reached",
    "insufficient_quota",
    "quota_exceeded",
    "limit_reached",
    "rate limit",
)


@dataclass(slots=True)
class UsageProbeParseResult:
    snapshot_status: str
    probe_status_code: int | None
    is_401: bool
    quota_status_code: int | None
    invalid_quota: bool
    quota_source: str | None
    weekly_used_percent: Decimal | None
    weekly_reset_at: datetime | None
    short_used_percent: Decimal | None
    short_reset_at: datetime | None
    remaining: Decimal | None
    limit_reached: bool | None
    allowed: bool | None
    raw_usage_json: dict[str, Any] | None
    error_message: str | None
    has_quota_observation: bool


def parse_usage_probe_response(
    response: dict[str, Any],
    *,
    status_message: Any,
    weekly_quota_threshold: Decimal,
    short_quota_threshold: Decimal,
) -> UsageProbeParseResult:
    quota_marked_by_status = _status_message_marks_quota(status_message)
    status_code = _coerce_int(response.get("status_code"))
    body = response.get("body")
    body_data = _as_json_obj(body)

    if status_code is None:
        invalid_quota = quota_marked_by_status or _contains_limit_error(response) or _contains_limit_error(body)
        return UsageProbeParseResult(
            snapshot_status="failed",
            probe_status_code=None,
            is_401=False,
            quota_status_code=None,
            invalid_quota=invalid_quota,
            quota_source="status_message" if invalid_quota else None,
            weekly_used_percent=None,
            weekly_reset_at=None,
            short_used_percent=None,
            short_reset_at=None,
            remaining=None,
            limit_reached=None,
            allowed=None,
            raw_usage_json=body_data,
            error_message="api-call 响应缺少 status_code",
            has_quota_observation=invalid_quota,
        )

    if status_code == 401:
        return UsageProbeParseResult(
            snapshot_status="success",
            probe_status_code=401,
            is_401=True,
            quota_status_code=401,
            invalid_quota=False,
            quota_source=None,
            weekly_used_percent=None,
            weekly_reset_at=None,
            short_used_percent=None,
            short_reset_at=None,
            remaining=None,
            limit_reached=None,
            allowed=None,
            raw_usage_json=body_data,
            error_message=None,
            has_quota_observation=False,
        )

    if status_code != 200:
        invalid_quota = quota_marked_by_status or _contains_limit_error(response) or _contains_limit_error(body)
        return UsageProbeParseResult(
            snapshot_status="partial_failed",
            probe_status_code=status_code,
            is_401=False,
            quota_status_code=status_code,
            invalid_quota=invalid_quota,
            quota_source="status_message" if invalid_quota else None,
            weekly_used_percent=None,
            weekly_reset_at=None,
            short_used_percent=None,
            short_reset_at=None,
            remaining=None,
            limit_reached=None,
            allowed=None,
            raw_usage_json=body_data,
            error_message=None,
            has_quota_observation=invalid_quota,
        )

    if body_data is None:
        return UsageProbeParseResult(
            snapshot_status="partial_failed",
            probe_status_code=200,
            is_401=False,
            quota_status_code=200,
            invalid_quota=quota_marked_by_status,
            quota_source="status_message" if quota_marked_by_status else None,
            weekly_used_percent=None,
            weekly_reset_at=None,
            short_used_percent=None,
            short_reset_at=None,
            remaining=None,
            limit_reached=None,
            allowed=None,
            raw_usage_json=None,
            error_message="usage body 不是有效 JSON 对象",
            has_quota_observation=quota_marked_by_status,
        )

    rate_limit = body_data.get("rate_limit") or body_data.get("rateLimit") or {}
    windows = _parse_windows(rate_limit)
    weekly_window, short_window = _pick_windows(windows)

    weekly_used_percent = weekly_window.used_percent if weekly_window is not None else None
    weekly_reset_at = weekly_window.reset_at if weekly_window is not None else None
    short_used_percent = short_window.used_percent if short_window is not None else None
    short_reset_at = short_window.reset_at if short_window is not None else None

    remaining = None
    for window in (weekly_window, short_window):
        if window is not None and window.remaining is not None:
            remaining = window.remaining
            break
    if remaining is None:
        remaining_candidates = [window.remaining for window in windows if window.remaining is not None]
        remaining = remaining_candidates[0] if remaining_candidates else None
    top_limit_reached = _coerce_bool(_pick_first(rate_limit, "limit_reached", "limitReached"))
    limit_reached = top_limit_reached
    if limit_reached is None:
        for window in (weekly_window, short_window):
            if window is not None and window.limit_reached is not None:
                limit_reached = window.limit_reached
                break

    allowed = _coerce_bool(_pick_first(rate_limit, "allowed"))
    if allowed is None:
        allowed = _coerce_bool(_pick_first(body_data, "allowed"))

    invalid_quota = False
    quota_source: str | None = None

    if weekly_used_percent is not None:
        quota_source = "weekly"
        invalid_quota = weekly_used_percent >= weekly_quota_threshold
    elif short_used_percent is not None:
        quota_source = "5hour"
        invalid_quota = short_used_percent >= short_quota_threshold
    else:
        remaining_zero = any(window.remaining == Decimal("0") for window in windows if window.remaining is not None)
        weekly_limit_reached = bool(weekly_window and weekly_window.limit_reached is True)
        short_limit_reached = bool(short_window and short_window.limit_reached is True)
        if weekly_limit_reached:
            invalid_quota = True
            quota_source = "weekly_limit"
        elif short_limit_reached:
            invalid_quota = True
            quota_source = "5hour_limit"
        elif remaining_zero:
            invalid_quota = True
            quota_source = "remaining"
        elif top_limit_reached is True or allowed is False:
            invalid_quota = True
            quota_source = "rate_limit_flag"
        elif quota_marked_by_status:
            invalid_quota = True
            quota_source = "status_message"

    has_quota_observation = any(
        value is not None
        for value in (
            weekly_used_percent,
            weekly_reset_at,
            short_used_percent,
            short_reset_at,
            remaining,
            limit_reached,
            allowed,
        )
    ) or invalid_quota

    return UsageProbeParseResult(
        snapshot_status="success",
        probe_status_code=200,
        is_401=False,
        quota_status_code=200,
        invalid_quota=invalid_quota,
        quota_source=quota_source,
        weekly_used_percent=weekly_used_percent,
        weekly_reset_at=weekly_reset_at,
        short_used_percent=short_used_percent,
        short_reset_at=short_reset_at,
        remaining=remaining,
        limit_reached=limit_reached,
        allowed=allowed,
        raw_usage_json=body_data,
        error_message=None,
        has_quota_observation=has_quota_observation,
    )


@dataclass(slots=True)
class _ParsedWindow:
    name: str
    used_percent: Decimal | None
    reset_at: datetime | None
    limit_window_seconds: int | None
    remaining: Decimal | None
    limit_reached: bool | None


def _parse_windows(rate_limit: Any) -> list[_ParsedWindow]:
    windows: list[_ParsedWindow] = []
    for key in (
        "primary_window",
        "secondary_window",
        "individual_window",
        "primaryWindow",
        "secondaryWindow",
        "individualWindow",
    ):
        window = rate_limit.get(key) if isinstance(rate_limit, dict) else None
        parsed = _parse_window(key, window)
        if parsed is not None:
            windows.append(parsed)
    return windows


def _pick_windows(windows: list[_ParsedWindow]) -> tuple[_ParsedWindow | None, _ParsedWindow | None]:
    weekly_window: _ParsedWindow | None = None
    short_window: _ParsedWindow | None = None

    for window in windows:
        lower_name = window.name.lower()
        if weekly_window is None and "individual" in lower_name:
            weekly_window = window
        if short_window is None and "secondary" in lower_name:
            short_window = window

    with_seconds = [window for window in windows if window.limit_window_seconds is not None]
    if weekly_window is None and with_seconds:
        weekly_window = max(with_seconds, key=lambda item: item.limit_window_seconds or 0)

    if short_window is None and with_seconds:
        sorted_windows = sorted(with_seconds, key=lambda item: item.limit_window_seconds or 0)
        if weekly_window is None:
            short_window = sorted_windows[0]
        else:
            for window in sorted_windows:
                if window.name != weekly_window.name:
                    short_window = window
                    break

    if weekly_window is None and windows:
        weekly_window = windows[0]

    if short_window is None and len(windows) > 1:
        for window in windows:
            if weekly_window is None or window.name != weekly_window.name:
                short_window = window
                break

    if (
        short_window is None
        and weekly_window is not None
        and weekly_window.limit_window_seconds is not None
        and weekly_window.limit_window_seconds <= 6 * 3600
    ):
        short_window = weekly_window
        weekly_window = None

    return weekly_window, short_window


def _parse_window(name: str, value: Any) -> _ParsedWindow | None:
    if not isinstance(value, dict):
        return None

    return _ParsedWindow(
        name=name,
        used_percent=_to_decimal(_pick_first(value, "used_percent", "usedPercent", "used_percentage")),
        reset_at=_parse_datetime(_pick_first(value, "reset_at", "resetAt")),
        limit_window_seconds=_coerce_int(
            _pick_first(
                value,
                "limit_window_seconds",
                "limitWindowSeconds",
                "window_seconds",
                "windowSeconds",
            )
        ),
        remaining=_to_decimal(_pick_first(value, "remaining")),
        limit_reached=_coerce_bool(_pick_first(value, "limit_reached", "limitReached")),
    )


def _pick_first(data: Any, *keys: str) -> Any:
    if not isinstance(data, dict):
        return None
    for key in keys:
        if data.get(key) is not None:
            return data.get(key)
    return None


def _status_message_marks_quota(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        texts = [value]
        parsed = _as_json_obj(value)
        if parsed is not None:
            texts.extend(_collect_texts(parsed))
    else:
        texts = _collect_texts(value)
    merged = " ".join(text.lower() for text in texts if text)
    return any(keyword in merged for keyword in LIMIT_KEYWORDS)


def _contains_limit_error(value: Any) -> bool:
    texts = _collect_texts(value)
    merged = " ".join(text.lower() for text in texts if text)
    return any(keyword in merged for keyword in LIMIT_KEYWORDS)


def _collect_texts(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, dict):
        texts: list[str] = []
        for child in value.values():
            texts.extend(_collect_texts(child))
        return texts
    if isinstance(value, list):
        texts: list[str] = []
        for child in value:
            texts.extend(_collect_texts(child))
        return texts
    return [str(value)]


def _as_json_obj(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        text = str(value).strip().rstrip("%")
        if not text:
            return None
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except ValueError:
        return None


def _coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None
