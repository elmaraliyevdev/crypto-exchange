"""Tests for matching engine behavior through the API (Celery eager mode)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.tasks.matching_engine import match_order
from tests.conftest import login_user, register_user


@pytest.mark.anyio
async def test_matching_executes_trade_and_updates_wallets(client: AsyncClient) -> None:
    await register_user(client, email="alice@example.com", username="alice", password="secret123")
    await register_user(client, email="bob@example.com", username="bob", password="secret123")

    alice_tokens = await login_user(client, email="alice@example.com", password="secret123")
    bob_tokens = await login_user(client, email="bob@example.com", password="secret123")
    alice_headers = {"Authorization": f"Bearer {alice_tokens['access_token']}"}
    bob_headers = {"Authorization": f"Bearer {bob_tokens['access_token']}"}

    # Fund wallets
    await client.post("/api/v1/wallets/deposit", headers=alice_headers, json={"currency": "USDT", "amount": "10000"})
    await client.post("/api/v1/wallets/deposit", headers=bob_headers, json={"currency": "BTC", "amount": "2"})

    # Place buy then sell at same price so they match
    buy = await client.post(
        "/api/v1/orders",
        headers=alice_headers,
        json={"pair": "BTC/USDT", "side": "buy", "price": "5000", "quantity": "1"},
    )
    assert buy.status_code == 201, buy.text

    sell = await client.post(
        "/api/v1/orders",
        headers=bob_headers,
        json={"pair": "BTC/USDT", "side": "sell", "price": "5000", "quantity": "1"},
    )
    assert sell.status_code == 201, sell.text

    # Celery eager mode runs the match inline; verify final balances
    alice_btc = await client.get("/api/v1/wallets/BTC", headers=alice_headers)
    assert alice_btc.status_code == 200
    assert alice_btc.json()["available"] == "1.00000000"

    alice_usdt = await client.get("/api/v1/wallets/USDT", headers=alice_headers)
    assert alice_usdt.status_code == 200
    assert alice_usdt.json()["available"] == "5000.00000000"
    assert alice_usdt.json()["reserved"] == "0E-8"

    bob_usdt = await client.get("/api/v1/wallets/USDT", headers=bob_headers)
    assert bob_usdt.status_code == 200
    assert bob_usdt.json()["available"] == "5000.00000000"

    bob_btc = await client.get("/api/v1/wallets/BTC", headers=bob_headers)
    assert bob_btc.status_code == 200
    assert bob_btc.json()["available"] == "1.00000000"
    assert bob_btc.json()["reserved"] == "0E-8"

    # Orders should be filled for both users
    alice_orders = await client.get("/api/v1/orders", headers=alice_headers)
    assert alice_orders.status_code == 200
    assert alice_orders.json()["items"][0]["status"] == "filled"

    bob_orders = await client.get("/api/v1/orders", headers=bob_headers)
    assert bob_orders.status_code == 200
    assert bob_orders.json()["items"][0]["status"] == "filled"

    trades = await client.get("/api/v1/trades/history", headers=alice_headers)
    assert trades.status_code == 200
    assert len(trades.json()["items"]) == 1

    # Replaying task for already-filled order should not create duplicate trades.
    match_order.delay(sell.json()["id"])
    trades_again = await client.get("/api/v1/trades/history", headers=alice_headers)
    assert trades_again.status_code == 200
    assert len(trades_again.json()["items"]) == 1
