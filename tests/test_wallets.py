"""Tests for wallet deposit/withdraw and invariants."""

from __future__ import annotations

from httpx import AsyncClient
import pytest

from tests.conftest import login_user, register_user


@pytest.mark.anyio
async def test_deposit_and_withdraw_updates_balances(client: AsyncClient) -> None:
    await register_user(client, email="alice@example.com", username="alice", password="secret123")
    tokens = await login_user(client, email="alice@example.com", password="secret123")
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    dep = await client.post("/api/v1/wallets/deposit", headers=headers, json={"currency": "USDT", "amount": "100"})
    assert dep.status_code == 200, dep.text
    assert dep.json()["available"] == "100.00000000"

    wd = await client.post("/api/v1/wallets/withdraw", headers=headers, json={"currency": "USDT", "amount": "40"})
    assert wd.status_code == 200, wd.text
    assert wd.json()["available"] == "60.00000000"


@pytest.mark.anyio
async def test_withdraw_rejects_insufficient_balance(client: AsyncClient) -> None:
    await register_user(client, email="alice@example.com", username="alice", password="secret123")
    tokens = await login_user(client, email="alice@example.com", password="secret123")
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    resp = await client.post("/api/v1/wallets/withdraw", headers=headers, json={"currency": "BTC", "amount": "1"})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Insufficient balance"
