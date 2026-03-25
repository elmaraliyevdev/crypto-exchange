"""Wallet API schemas: deposits, withdrawals, balances, and address responses."""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WalletResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    currency: str
    available: Decimal
    reserved: Decimal
    total: Decimal


class DepositRequest(BaseModel):
    currency: str = Field(min_length=1, max_length=16)
    amount: Decimal = Field(gt=0)

    @field_validator("currency")
    @classmethod
    def currency_uppercase(cls, v: str) -> str:
        return v.upper()


class WithdrawRequest(BaseModel):
    currency: str = Field(min_length=1, max_length=16)
    amount: Decimal = Field(gt=0)

    @field_validator("currency")
    @classmethod
    def currency_uppercase(cls, v: str) -> str:
        return v.upper()
