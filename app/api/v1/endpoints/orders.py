"""Order endpoints: create, cancel, and query open/historical orders."""

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db
from app.models.order import Order, OrderStatus
from app.models.trade import Trade
from app.models.user import User
from app.schemas.order import CancelResponse, OrderBook, OrderCreate, OrderListResponse, OrderResponse
from app.schemas.trade import TradeListResponse, TradeResponse
from app.services import order_service

router = APIRouter()

_DEFAULT_LIMIT = 100
_MAX_LIMIT = 100


@router.get("/trades/history", response_model=TradeListResponse)
async def trade_history(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    limit: int = Query(default=_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> TradeListResponse:
    trades, total = await order_service.get_trade_history(
        db, current_user.id, limit=limit, offset=offset
    )
    return TradeListResponse(items=trades, total=total, limit=limit, offset=offset)


@router.post("/orders", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    body: OrderCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> Order:
    return await order_service.place_order(
        db,
        user_id=current_user.id,
        pair=body.pair,
        side=body.side,
        price=body.price,
        quantity=body.quantity,
    )


@router.delete("/orders/{order_id}", response_model=CancelResponse)
async def cancel_order(
    order_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> Order:
    return await order_service.cancel_order(db, current_user.id, order_id)


@router.get("/orders", response_model=OrderListResponse)
async def list_orders(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    limit: int = Query(default=_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> OrderListResponse:
    orders, total = await order_service.get_user_orders(
        db, current_user.id, status_filter, limit=limit, offset=offset
    )
    return OrderListResponse(items=orders, total=total, limit=limit, offset=offset)


@router.get("/orders/open", response_model=OrderListResponse)
async def list_open_orders(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    limit: int = Query(default=_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> OrderListResponse:
    orders, total = await order_service.get_user_open_orders(
        db, current_user.id, limit=limit, offset=offset
    )
    return OrderListResponse(items=orders, total=total, limit=limit, offset=offset)


@router.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> Order:
    return await order_service.get_order(db, current_user.id, order_id)


@router.get("/order-book/{pair}", response_model=OrderBook)
async def order_book(pair: str, db: Annotated[AsyncSession, Depends(get_db)]) -> dict:
    normalized = pair.replace("-", "/").upper()
    return await order_service.get_order_book(db, normalized)
