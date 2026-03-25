"""Order book matching: price-time priority, fills, and trade persistence triggers."""

from __future__ import annotations

import logging
from decimal import Decimal

from sqlalchemy import asc, desc, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import create_engine

from app.core.config import settings
from app.db.base import Base
from app.models.order import Order, OrderSide, OrderStatus
from app.models.trade import Trade
from app.models.wallet import Wallet
from app.tasks.celery_app import celery_app

log = logging.getLogger(__name__)


def _sync_database_url() -> str:
    url = settings.DATABASE_URL
    if "+asyncpg" in url:
        return url.replace("+asyncpg", "+psycopg2", 1)
    return url


_sync_engine: Engine = create_engine(_sync_database_url(), pool_pre_ping=True)
SessionLocal = sessionmaker(bind=_sync_engine, class_=Session, expire_on_commit=False)


def _parse_pair(pair: str) -> tuple[str, str, str]:
    raw = pair.strip().upper()
    if "/" not in raw or raw.count("/") != 1:
        raise ValueError("Invalid pair format")
    base, quote = raw.split("/", 1)
    if not base or not quote:
        raise ValueError("Invalid pair format")
    return raw, base, quote


def _wallet_for_update(session: Session, *, user_id: int, currency: str) -> Wallet:
    stmt = (
        select(Wallet)
        .where(Wallet.user_id == user_id, Wallet.currency == currency)
        .with_for_update()
    )
    wallet = session.execute(stmt).scalar_one_or_none()
    if wallet is None:
        wallet = Wallet(user_id=user_id, currency=currency, available=Decimal("0"), reserved=Decimal("0"))
        session.add(wallet)
        session.flush()
        session.refresh(wallet)
    return wallet


@celery_app.task(name="match_order", bind=True, max_retries=3)
def match_order(self, order_id: int) -> None:
    try:
        with SessionLocal() as session:
            with session.begin():
                taker_stmt = (
                    select(Order)
                    .where(Order.id == order_id)
                    .with_for_update(skip_locked=True)
                )
                taker = session.execute(taker_stmt).scalar_one_or_none()
                if taker is None:
                    return
                if taker.status not in (OrderStatus.open, OrderStatus.partially_filled):
                    return

                pair, base, quote = _parse_pair(taker.pair)

                def next_maker() -> Order | None:
                    statuses = (OrderStatus.open, OrderStatus.partially_filled)
                    if taker.side == OrderSide.buy:
                        stmt = (
                            select(Order)
                            .where(
                                Order.pair == pair,
                                Order.side == OrderSide.sell,
                                Order.status.in_(statuses),
                                Order.price <= taker.price,
                                (Order.quantity - Order.filled_quantity) > 0,
                            )
                            .order_by(asc(Order.price), asc(Order.created_at), asc(Order.id))
                            .limit(1)
                            .with_for_update(skip_locked=True)
                        )
                    else:
                        stmt = (
                            select(Order)
                            .where(
                                Order.pair == pair,
                                Order.side == OrderSide.buy,
                                Order.status.in_(statuses),
                                Order.price >= taker.price,
                                (Order.quantity - Order.filled_quantity) > 0,
                            )
                            .order_by(desc(Order.price), asc(Order.created_at), asc(Order.id))
                            .limit(1)
                            .with_for_update(skip_locked=True)
                        )
                    return session.execute(stmt).scalar_one_or_none()

                while taker.remaining > 0:
                    maker = next_maker()
                    if maker is None:
                        break

                    fill_qty = min(taker.remaining, maker.remaining)
                    trade_price = maker.price

                    taker.filled_quantity += fill_qty
                    taker.status = (
                        OrderStatus.filled if taker.remaining <= 0 else OrderStatus.partially_filled
                    )

                    maker.filled_quantity += fill_qty
                    maker.status = (
                        OrderStatus.filled if maker.remaining <= 0 else OrderStatus.partially_filled
                    )

                    if taker.side == OrderSide.buy:
                        buyer = taker
                        seller = maker
                    else:
                        buyer = maker
                        seller = taker

                    buyer_quote = _wallet_for_update(session, user_id=buyer.user_id, currency=quote)
                    buyer_base = _wallet_for_update(session, user_id=buyer.user_id, currency=base)
                    seller_base = _wallet_for_update(session, user_id=seller.user_id, currency=base)
                    seller_quote = _wallet_for_update(session, user_id=seller.user_id, currency=quote)

                    cost = fill_qty * trade_price

                    buyer_quote.reserved -= cost
                    buyer_base.available += fill_qty

                    seller_base.reserved -= fill_qty
                    seller_quote.available += cost

                    if (
                        buyer_quote.available < 0
                        or buyer_quote.reserved < 0
                        or buyer_base.available < 0
                        or buyer_base.reserved < 0
                        or seller_base.available < 0
                        or seller_base.reserved < 0
                        or seller_quote.available < 0
                        or seller_quote.reserved < 0
                    ):
                        raise ValueError("Wallet balance invariant violated")

                    trade = Trade(
                        pair=pair,
                        maker_order_id=maker.id,
                        taker_order_id=taker.id,
                        buyer_id=buyer.user_id,
                        seller_id=seller.user_id,
                        price=trade_price,
                        quantity=fill_qty,
                    )
                    session.add(trade)
                    session.flush()

                    log.info(
                        "Trade executed: pair=%s maker_order_id=%s taker_order_id=%s buyer_id=%s seller_id=%s price=%s quantity=%s",
                        pair,
                        maker.id,
                        taker.id,
                        buyer.user_id,
                        seller.user_id,
                        trade_price,
                        fill_qty,
                    )
    except ValueError:
        # Deterministic/business-rule validation failures should not be retried.
        raise
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2**self.request.retries)
