"""Pytest fixtures for integration-style API tests.

These tests expect a real PostgreSQL database configured via DATABASE_URL.
Run with docker services up (db + redis) and migrations applied.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator, Generator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import redis.asyncio as aioredis

from app.core.dependencies import get_db, get_redis
from app.main import app
from app.tasks.celery_app import celery_app


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    # httpx AsyncClient + pytest uses anyio.
    return "asyncio"


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL must be set to run tests")
    return url


@pytest.fixture
async def async_engine(database_url: str) -> AsyncGenerator[AsyncEngine, None]:
    """Function-scoped engine avoids cross-event-loop issues."""
    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
def async_session_factory(async_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )


@pytest.fixture(autouse=True)
def celery_eager_mode() -> Generator[None, None, None]:
    """Force Celery tasks to run inline during tests."""
    prev_always_eager = celery_app.conf.task_always_eager
    prev_eager_propagates = celery_app.conf.task_eager_propagates
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    yield
    celery_app.conf.task_always_eager = prev_always_eager
    celery_app.conf.task_eager_propagates = prev_eager_propagates


@pytest.fixture
async def db_session(async_session_factory: async_sessionmaker[AsyncSession]) -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        # Clean slate per test.
        await session.execute(text("TRUNCATE trades, orders, wallets, users RESTART IDENTITY CASCADE;"))
        await session.commit()
        yield session


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    redis = aioredis.from_url("redis://127.0.0.1:6379/0", encoding="utf-8", decode_responses=True)

    def _override_get_redis() -> aioredis.Redis:
        return redis

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_redis] = _override_get_redis
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
    await redis.aclose()


async def register_user(client: AsyncClient, *, email: str, username: str, password: str) -> dict:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "username": username, "password": password},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def login_user(client: AsyncClient, *, email: str, password: str) -> dict:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()
