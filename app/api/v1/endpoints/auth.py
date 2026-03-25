"""Authentication endpoints: register, login, refresh, and logout."""

from typing import Annotated, Any, cast

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db, get_redis
from app.models.user import User
from app.schemas.auth import (
    AccessToken,
    LoginJSON,
    RefreshRequest,
    TokenPair,
    UserRegister,
    UserResponse,
)
from app.services import auth_service

router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: UserRegister,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    return await auth_service.register_user(
        db,
        email=body.email,
        username=body.username,
        password=body.password,
    )


@router.post("/login", response_model=TokenPair)
async def login(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[aioredis.Redis, Depends(get_redis)],
) -> dict[str, str]:
    """Accepts JSON (`email`, `password`) or OAuth2 client form (`username` = email, `password`)."""
    content_type = request.headers.get("content-type", "").lower()
    email: str
    password: str

    if "application/json" in content_type:
        try:
            raw = await request.json()
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid JSON body",
            ) from exc
        try:
            payload = LoginJSON.model_validate(raw)
        except ValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=cast(list[Any], exc.errors()),
            ) from exc
        email = str(payload.email)
        password = payload.password
    else:
        form = await request.form()
        username_field = form.get("username")
        password_field = form.get("password")
        if not username_field or not password_field:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="OAuth2 form requires username (email) and password",
            )
        email = str(username_field)
        password = str(password_field)

    user = await auth_service.authenticate_user(db, email=email, password=password)
    return await auth_service.create_token_pair(user.id, redis)


@router.post("/refresh", response_model=AccessToken)
async def refresh(
    body: RefreshRequest,
    redis: Annotated[aioredis.Redis, Depends(get_redis)],
) -> dict[str, str]:
    return await auth_service.refresh_access_token(body.refresh_token, redis)


@router.post("/logout")
async def logout(
    current_user: Annotated[User, Depends(get_current_user)],
    redis: Annotated[aioredis.Redis, Depends(get_redis)],
) -> dict[str, str]:
    await auth_service.logout_user(current_user.id, redis)
    return {"message": "logged out"}
