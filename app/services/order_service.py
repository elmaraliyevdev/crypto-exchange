"""Order validation, wallet locking, order book queries, and lifecycle updates."""

from __future__ import annotations

from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import Select, asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order, OrderSide, OrderStatus
from app.models.trade import Trade
from app.models.wallet import Wallet

# Orders that can still appear on the book or be cancelled.
OPEN_ORDER_STATUSES: tuple[OrderStatus, ...] = (OrderStatus.open, OrderStatus.partially_filled)


def _parse_pair(pair: str) -> tuple[str, str, str]:
    raw = pair.strip().upper()
    if "/" not in raw or raw.count("/") != 1:
        raise HTTPException(status_code=400, detail="Invalid pair format")
    base, quote = raw.split("/", 1)
    if not base or not quote:
        raise HTTPException(status_code=400, detail="Invalid pair format")
    return raw, base, quote


async def _load_wallet_for_update(
    db: AsyncSession, *, user_id: int, currency: str
) -> Wallet:
    stmt: Select[tuple[Wallet]] = (
        select(Wallet)
        .where(Wallet.user_id == user_id, Wallet.currency == currency)
        .with_for_update()
    )
    result = await db.execute(stmt)
    wallet = result.scalar_one_or_none()
    if wallet is None:
        wallet = Wallet(user_id=user_id, currency=currency, available=Decimal("0"), reserved=Decimal("0"))
        db.add(wallet)
        await db.flush()
        await db.refresh(wallet)
    return wallet


async def place_order(
    db: AsyncSession,
    user_id: int,
    pair: str,
    side: OrderSide | str,
    price: Decimal,
    quantity: Decimal,
) -> Order:
    pair_norm, base, quote = _parse_pair(pair)
    side_enum = OrderSide(side) if not isinstance(side, OrderSide) else side

    await db.rollback()
    async with db.begin():
        if side_enum == OrderSide.buy:
            cost = price * quantity
            wallet = await _load_wallet_for_update(db, user_id=user_id, currency=quote)
            if wallet.available < cost:
                raise HTTPException(status_code=400, detail="Insufficient balance")
            wallet.available -= cost
            wallet.reserved += cost
        else:
            wallet = await _load_wallet_for_update(db, user_id=user_id, currency=base)
            if wallet.available < quantity:
                raise HTTPException(status_code=400, detail="Insufficient balance")
            wallet.available -= quantity
            wallet.reserved += quantity

        if wallet.available < 0 or wallet.reserved < 0:
            raise HTTPException(status_code=400, detail="Invalid balance")

        order = Order(
            user_id=user_id,
            pair=pair_norm,
            side=side_enum,
            status=OrderStatus.open,
            price=price,
            quantity=quantity,
            filled_quantity=Decimal("0"),
        )
        db.add(order)
        await db.flush()
        await db.refresh(order)

    from app.tasks.matching_engine import match_order

    match_order.delay(order.id)
    return order


async def cancel_order(db: AsyncSession, user_id: int, order_id: int) -> Order:
    await db.rollback()
    async with db.begin():
        order_stmt: Select[tuple[Order]] = select(Order).where(Order.id == order_id).with_for_update()
        result = await db.execute(order_stmt)
        order = result.scalar_one_or_none()
        if order is None:
            raise HTTPException(status_code=404, detail="Order not found")
        if order.user_id != user_id:
            raise HTTPException(status_code=403, detail="Forbidden")
        if order.status not in (OrderStatus.open, OrderStatus.partially_filled):
            raise HTTPException(status_code=400, detail="Order cannot be cancelled")

        pair_norm, base, quote = _parse_pair(order.pair)
        _ = pair_norm

        refund: Decimal
        refund_currency: str
        if order.side == OrderSide.buy:
            refund = order.remaining * order.price
            refund_currency = quote
        else:
            refund = order.remaining
            refund_currency = base

        wallet = await _load_wallet_for_update(db, user_id=user_id, currency=refund_currency)
        wallet.reserved -= refund
        wallet.available += refund

        if wallet.available < 0 or wallet.reserved < 0:
            raise HTTPException(status_code=400, detail="Invalid balance")

        order.status = OrderStatus.cancelled
        await db.flush()
        await db.refresh(order)
    return order


async def get_order(db: AsyncSession, user_id: int, order_id: int) -> Order:
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.user_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return order


def _status_enum(status: OrderStatus | str | None) -> OrderStatus | None:
    if status is None:
        return None
    return OrderStatus(status) if not isinstance(status, OrderStatus) else status


async def get_user_orders(
    db: AsyncSession,
    user_id: int,
    status: OrderStatus | str | None = None,
    *,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[Order], int]:
    status_enum = _status_enum(status)
    filters = [Order.user_id == user_id]
    if status_enum is not None:
        filters.append(Order.status == status_enum)

    count_stmt = select(func.count()).select_from(Order).where(*filters)
    total = int((await db.execute(count_stmt)).scalar_one())

    stmt = (
        select(Order)
        .where(*filters)
        .order_by(desc(Order.created_at), desc(Order.id))
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all()), total


async def get_user_open_orders(
    db: AsyncSession,
    user_id: int,
    *,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[Order], int]:
    filters = [Order.user_id == user_id, Order.status.in_(OPEN_ORDER_STATUSES)]
    count_stmt = select(func.count()).select_from(Order).where(*filters)
    total = int((await db.execute(count_stmt)).scalar_one())

    stmt = (
        select(Order)
        .where(*filters)
        .order_by(desc(Order.created_at), desc(Order.id))
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all()), total


async def get_order_book(db: AsyncSession, pair: str) -> dict:
    pair_norm, _, _ = _parse_pair(pair)
    statuses = (OrderStatus.open, OrderStatus.partially_filled)
    remaining_expr = (Order.quantity - Order.filled_quantity).label("remaining")

    bid_stmt = (
        select(Order.price, remaining_expr)
        .where(
            Order.pair == pair_norm,
            Order.side == OrderSide.buy,
            Order.status.in_(statuses),
            (Order.quantity - Order.filled_quantity) > 0,
        )
        .order_by(desc(Order.price), asc(Order.created_at), asc(Order.id))
    )
    ask_stmt = (
        select(Order.price, remaining_expr)
        .where(
            Order.pair == pair_norm,
            Order.side == OrderSide.sell,
            Order.status.in_(statuses),
            (Order.quantity - Order.filled_quantity) > 0,
        )
        .order_by(asc(Order.price), asc(Order.created_at), asc(Order.id))
    )

    bids_rows = (await db.execute(bid_stmt)).all()
    asks_rows = (await db.execute(ask_stmt)).all()

    return {
        "pair": pair_norm,
        "bids": [{"price": price, "quantity": qty} for price, qty in bids_rows],
        "asks": [{"price": price, "quantity": qty} for price, qty in asks_rows],
    }


async def get_trade_history(
    db: AsyncSession,
    user_id: int,
    *,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[Trade], int]:
    user_filter = (Trade.buyer_id == user_id) | (Trade.seller_id == user_id)
    count_stmt = select(func.count()).select_from(Trade).where(user_filter)
    total = int((await db.execute(count_stmt)).scalar_one())

    stmt = (
        select(Trade)
        .where(user_filter)
        .order_by(desc(Trade.executed_at), desc(Trade.id))
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all()), total
