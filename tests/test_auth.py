"""Tests for registration, login, and auth protection."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.conftest import login_user, register_user


@pytest.mark.anyio
async def test_register_and_login_returns_token_pair(client: AsyncClient) -> None:
    await register_user(
        client,
        email="alice@example.com",
        username="alice",
        password="secret123",
    )
    tokens = await login_user(client, email="alice@example.com", password="secret123")
    assert "access_token" in tokens
    assert "refresh_token" in tokens
    assert tokens.get("token_type") == "bearer"


@pytest.mark.anyio
async def test_protected_endpoint_requires_bearer_token(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/wallets")
    assert resp.status_code == 401
