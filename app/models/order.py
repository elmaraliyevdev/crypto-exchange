"""Order model: side, type, price, quantity, status, and market/pair references."""

from __future__ import annotations

import datetime
import enum
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.trade import Trade
    from app.models.user import User


class OrderSide(str, enum.Enum):
    buy = "buy"
    sell = "sell"


class OrderStatus(str, enum.Enum):
    open = "open"
    partially_filled = "partially_filled"
    filled = "filled"
    cancelled = "cancelled"


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    pair: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    side: Mapped[OrderSide] = mapped_column(
        SAEnum(OrderSide, native_enum=False),
        nullable=False,
    )
    status: Mapped[OrderStatus] = mapped_column(
        SAEnum(OrderStatus, native_enum=False),
        nullable=False,
        default=OrderStatus.open,
        index=True,
    )
    price: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    filled_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 8),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=datetime.datetime.now(datetime.timezone.utc),
    )

    user: Mapped[User] = relationship(back_populates="orders", lazy="selectin")
    trades_as_maker: Mapped[list[Trade]] = relationship(
        "Trade",
        foreign_keys="Trade.maker_order_id",
        back_populates="maker_order",
        lazy="selectin",
    )
    trades_as_taker: Mapped[list[Trade]] = relationship(
        "Trade",
        foreign_keys="Trade.taker_order_id",
        back_populates="taker_order",
        lazy="selectin",
    )

    @property
    def remaining(self) -> Decimal:
        return self.quantity - self.filled_quantity
