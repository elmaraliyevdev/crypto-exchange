"""Aggregates v1 endpoint routers under a single APIRouter with prefix and tags."""

from fastapi import APIRouter

from app.api.v1.endpoints import auth, orders, wallets

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(wallets.router, prefix="/wallets", tags=["wallets"])
api_router.include_router(orders.router, prefix="", tags=["orders"])
