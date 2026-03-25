"""User registration, authentication, token issuance, and session-related logic."""

import hashlib

import redis.asyncio as aioredis
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User


async def register_user(
    db: AsyncSession,
    email: str,
    username: str,
    password: str,
) -> User:
    dup_email = await db.execute(select(User.id).where(User.email == email))
    if dup_email.first() is not None:
        raise HTTPException(status_code=400, detail="Email already registered")
    dup_username = await db.execute(select(User.id).where(User.username == username))
    if dup_username.first() is not None:
        raise HTTPException(status_code=400, detail="Username already taken")

    # SELECT autobegins a transaction; close it before starting the write block.
    await db.rollback()

    async with db.begin():
        user = User(
            email=email,
            username=username,
            hashed_password=hash_password(password),
        )
        db.add(user)
        await db.flush()
        await db.refresh(user)
    return user


async def authenticate_user(
    db: AsyncSession,
    email: str,
    password: str,
) -> User:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    return user


async def create_token_pair(
    user_id: int,
    redis: aioredis.Redis,
) -> dict[str, str]:
    access_token = create_access_token(user_id)
    refresh_token = create_refresh_token(user_id)
    digest = hashlib.sha256(refresh_token.encode()).hexdigest()
    ttl_seconds = settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600
    await redis.set(f"refresh:{user_id}", digest, ex=ttl_seconds)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


async def refresh_access_token(
    refresh_token: str,
    redis: aioredis.Redis,
) -> dict[str, str]:
    try:
        payload = decode_token(refresh_token)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid refresh token") from None
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    sub = payload.get("sub")
    if sub is None:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    try:
        user_id = int(sub)
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    stored = await redis.get(f"refresh:{user_id}")
    if stored is None:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    if stored != hashlib.sha256(refresh_token.encode()).hexdigest():
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    access_token = create_access_token(user_id)
    return {
        "access_token": access_token,
        "token_type": "bearer",
    }


async def logout_user(user_id: int, redis: aioredis.Redis) -> None:
    await redis.delete(f"refresh:{user_id}")
