"""Tests for order placement and cancellation."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.conftest import login_user, register_user


@pytest.mark.anyio
async def test_place_buy_order_reserves_quote_balance(client: AsyncClient) -> None:
    await register_user(client, email="alice@example.com", username="alice", password="secret123")
    tokens = await login_user(client, email="alice@example.com", password="secret123")
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    await client.post("/api/v1/wallets/deposit", headers=headers, json={"currency": "USDT", "amount": "10000"})

    place = await client.post(
        "/api/v1/orders",
        headers=headers,
        json={"pair": "BTC/USDT", "side": "buy", "price": "5000", "quantity": "1"},
    )
    assert place.status_code == 201, place.text
    assert place.json()["status"] == "open"

    usdt = await client.get("/api/v1/wallets/USDT", headers=headers)
    assert usdt.status_code == 200
    body = usdt.json()
    assert body["available"] == "5000.00000000"
    assert body["reserved"] == "5000.00000000"


@pytest.mark.anyio
async def test_cancel_order_refunds_reserved_balance(client: AsyncClient) -> None:
    await register_user(client, email="alice@example.com", username="alice", password="secret123")
    tokens = await login_user(client, email="alice@example.com", password="secret123")
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    await client.post("/api/v1/wallets/deposit", headers=headers, json={"currency": "USDT", "amount": "10000"})
    place = await client.post(
        "/api/v1/orders",
        headers=headers,
        json={"pair": "BTC/USDT", "side": "buy", "price": "5000", "quantity": "1"},
    )
    order_id = place.json()["id"]

    cancel = await client.delete(f"/api/v1/orders/{order_id}", headers=headers)
    assert cancel.status_code == 200, cancel.text
    assert cancel.json()["status"] == "cancelled"

    usdt = await client.get("/api/v1/wallets/USDT", headers=headers)
    body = usdt.json()
    from decimal import Decimal

    assert Decimal(body["available"]).quantize(Decimal("0.00000000")) == Decimal("10000.00000000")
    assert Decimal(body["reserved"]).quantize(Decimal("0.00000000")) == Decimal("0.00000000")


@pytest.mark.anyio
async def test_list_open_orders_excludes_filled(client: AsyncClient) -> None:
    await register_user(client, email="alice@example.com", username="alice", password="secret123")
    tokens = await login_user(client, email="alice@example.com", password="secret123")
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    await client.post("/api/v1/wallets/deposit", headers=headers, json={"currency": "USDT", "amount": "10000"})
    await client.post(
        "/api/v1/orders",
        headers=headers,
        json={"pair": "BTC/USDT", "side": "buy", "price": "5000", "quantity": "1"},
    )

    open_resp = await client.get("/api/v1/orders/open", headers=headers)
    assert open_resp.status_code == 200
    body = open_resp.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["status"] == "open"

    order_id = body["items"][0]["id"]
    await client.delete(f"/api/v1/orders/{order_id}", headers=headers)

    open_after = await client.get("/api/v1/orders/open", headers=headers)
    assert open_after.json()["total"] == 0
    assert open_after.json()["items"] == []


@pytest.mark.anyio
async def test_orders_and_trades_pagination_meta(client: AsyncClient) -> None:
    await register_user(client, email="alice@example.com", username="alice", password="secret123")
    tokens = await login_user(client, email="alice@example.com", password="secret123")
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    orders = await client.get("/api/v1/orders", headers=headers, params={"limit": 10, "offset": 0})
    assert orders.status_code == 200
    data = orders.json()
    assert "items" in data and "total" in data and "limit" in data and "offset" in data
    assert data["limit"] == 10
    assert data["offset"] == 0

    trades = await client.get("/api/v1/trades/history", headers=headers, params={"limit": 5, "offset": 0})
    assert trades.status_code == 200
    td = trades.json()
    assert td["limit"] == 5
    assert td["total"] == 0
