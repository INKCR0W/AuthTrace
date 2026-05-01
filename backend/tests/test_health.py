from __future__ import annotations

import asyncio

import httpx

from app.main import app


async def _get(path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.get(path)


async def _options(path: str, *, origin: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.options(
            path,
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
            },
        )


def test_root_health() -> None:
    response = asyncio.run(_get("/health"))

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_api_health() -> None:
    response = asyncio.run(_get("/api/v1/health"))

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_api_health_cors_preflight() -> None:
    response = asyncio.run(_options("/api/v1/health", origin="http://localhost:5173"))

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
