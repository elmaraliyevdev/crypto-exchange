"""Order placement, cancellation, and listing request/response shapes."""

import re
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.order import OrderSide, OrderStatus

_PAIR_RE = re.compile(r"^[A-Z0-9]{2,16}/[A-Z0-9]{2,16}$")


class OrderCreate(BaseModel):
    pair: str
    side: OrderSide
    price: Decimal = Field(gt=0)
    quantity: Decimal = Field(gt=0)

    @field_validator("pair")
    @classmethod
    def pair_base_quote(cls, v: str) -> str:
        pair = v.strip().upper()
        if not _PAIR_RE.fullmatch(pair):
            raise ValueError("pair must be in BASE/QUOTE format")
        return pair


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pair: str
    side: OrderSide
    status: OrderStatus
    price: Decimal
    quantity: Decimal
    filled_quantity: Decimal
    remaining: Decimal
    created_at: Any


class OrderBookEntry(BaseModel):
    price: Decimal
    quantity: Decimal


class OrderBook(BaseModel):
    pair: str
    bids: list[OrderBookEntry]
    asks: list[OrderBookEntry]


class CancelResponse(OrderResponse):
    pass


class OrderListResponse(BaseModel):
    """Paginated list of orders."""

    items: list[OrderResponse]
    total: int
    limit: int
    offset: int
