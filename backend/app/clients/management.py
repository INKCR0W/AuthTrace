from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.core.config import Settings


class ManagementApiError(RuntimeError):
    pass


class ManagementApiClient:
    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        timeout_seconds: float,
        request_retries: int,
        retry_backoff_seconds: float,
        user_agent: str,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout_seconds = timeout_seconds
        self.request_retries = request_retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self.user_agent = user_agent

    @classmethod
    def from_settings(cls, settings: Settings) -> "ManagementApiClient":
        if not settings.management_base_url or not settings.management_token:
            raise ManagementApiError("management source config is incomplete")

        return cls(
            base_url=settings.management_base_url,
            token=settings.management_token,
            timeout_seconds=settings.management_timeout_seconds,
            request_retries=settings.management_request_retries,
            retry_backoff_seconds=settings.management_retry_backoff_seconds,
            user_agent=settings.management_user_agent,
        )

    async def refresh_config(self) -> None:
        await self._request("GET", "/v0/management/config.yaml")

    async def list_auth_files(self) -> list[dict[str, Any]]:
        payload = await self._request_json("GET", "/v0/management/auth-files")
        files = payload.get("files")
        if not isinstance(files, list):
            raise ManagementApiError("management auth-files response missing files")

        return [item for item in files if isinstance(item, dict)]

    async def probe_usage(
        self,
        *,
        auth_index: str,
        chatgpt_account_id: str | None = None,
    ) -> dict[str, Any]:
        call_header: dict[str, str] = {
            "Authorization": "Bearer $TOKEN$",
            "Content-Type": "application/json",
            "User-Agent": self.user_agent,
        }
        if chatgpt_account_id:
            call_header["Chatgpt-Account-Id"] = chatgpt_account_id

        payload = {
            "authIndex": auth_index,
            "method": "GET",
            "url": "https://chatgpt.com/backend-api/wham/usage",
            "header": call_header,
        }
        response = await self._request_json("POST", "/v0/management/api-call", json=payload)
        if "status_code" not in response:
            raise ManagementApiError("management api-call response missing status_code")
        return response

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = await self._request(method, path, json=json)
        try:
            payload = response.json()
        except ValueError as exc:
            raise ManagementApiError(f"management response is not valid json: {path}") from exc

        if not isinstance(payload, dict):
            raise ManagementApiError(f"management response is not an object: {path}")

        return payload

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> httpx.Response:
        attempts = self.request_retries + 1
        last_error: ManagementApiError | None = None

        for attempt in range(1, attempts + 1):
            try:
                async with httpx.AsyncClient(
                    base_url=self.base_url,
                    headers=self._default_headers(),
                    timeout=self.timeout_seconds,
                ) as client:
                    response = await client.request(method, path, json=json)
            except httpx.TransportError as exc:
                last_error = ManagementApiError(
                    f"management request transport error: {method} {path} -> {exc}"
                )
                if attempt < attempts:
                    await self._sleep_before_retry(attempt)
                    continue
                raise last_error from exc

            if response.status_code >= 400:
                detail = response.text[:200]
                last_error = ManagementApiError(
                    f"management request failed: {method} {path} -> {response.status_code} {detail}"
                )
                if attempt < attempts and _is_retryable_status_code(response.status_code):
                    await self._sleep_before_retry(attempt)
                    continue
                raise last_error

            return response

        if last_error is not None:
            raise last_error
        raise ManagementApiError(f"management request failed without response: {method} {path}")

    async def _sleep_before_retry(self, attempt: int) -> None:
        if self.retry_backoff_seconds <= 0:
            return
        await asyncio.sleep(self.retry_backoff_seconds * attempt)

    def _default_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        }


def _is_retryable_status_code(status_code: int) -> bool:
    return status_code == 429 or status_code >= 500
