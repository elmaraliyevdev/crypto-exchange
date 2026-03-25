"""Trade history and public tape schemas for API responses."""

from decimal import Decimal
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TradeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pair: str
    maker_order_id: int
    taker_order_id: int
    buyer_id: int
    seller_id: int
    price: Decimal
    quantity: Decimal
    executed_at: datetime


class TradeListResponse(BaseModel):
    """Paginated trade history."""

    items: list[TradeResponse]
    total: int
    limit: int
    offset: int
