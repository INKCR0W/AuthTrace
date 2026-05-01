from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import httpx
import pytest

from app.clients.management import ManagementApiClient, ManagementApiError


def _build_client(
    *,
    request_retries: int = 2,
    retry_backoff_seconds: float = 0.0,
) -> ManagementApiClient:
    return ManagementApiClient(
        base_url="http://management.local",
        token="secret",
        timeout_seconds=5.0,
        request_retries=request_retries,
        retry_backoff_seconds=retry_backoff_seconds,
        user_agent="AuthTrace-Test/1.0",
    )


def test_list_auth_files_retries_on_retryable_http_status(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503, text="upstream busy", request=request)
        return httpx.Response(200, json={"files": [{"auth_index": "auth-1"}]}, request=request)

    monkeypatch.setattr(httpx, "AsyncClient", _build_async_client_factory(handler))
    client = _build_client(request_retries=1)

    auth_files = _run(client.list_auth_files())

    assert attempts == 2
    assert auth_files == [{"auth_index": "auth-1"}]


def test_list_auth_files_does_not_retry_on_non_retryable_http_status(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(400, text="bad request", request=request)

    monkeypatch.setattr(httpx, "AsyncClient", _build_async_client_factory(handler))
    client = _build_client(request_retries=3)

    with pytest.raises(ManagementApiError, match="400"):
        _run(client.list_auth_files())

    assert attempts == 1


def test_probe_usage_retries_on_transport_error(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ReadTimeout("timed out", request=request)
        return httpx.Response(200, json={"status_code": 200, "body": {}}, request=request)

    monkeypatch.setattr(httpx, "AsyncClient", _build_async_client_factory(handler))
    client = _build_client(request_retries=1)

    payload = _run(client.probe_usage(auth_index="auth-1"))

    assert attempts == 2
    assert payload["status_code"] == 200


def test_refresh_config_raises_after_retry_exhausted(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(429, text="too many requests", request=request)

    monkeypatch.setattr(httpx, "AsyncClient", _build_async_client_factory(handler))
    client = _build_client(request_retries=2)

    with pytest.raises(ManagementApiError, match="429"):
        _run(client.refresh_config())

    assert attempts == 3


def _build_async_client_factory(
    handler: Callable[[httpx.Request], httpx.Response],
) -> type[httpx.AsyncClient]:
    class _PatchedAsyncClient(httpx.AsyncClient):
        def __init__(self, *args: object, **kwargs: object) -> None:
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    return _PatchedAsyncClient


def _run(awaitable: Awaitable[object]) -> object:
    return asyncio.run(awaitable)
