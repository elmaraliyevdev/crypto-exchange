"""Wallet and balance operations: ledger updates, locks, and transfer rules."""

from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.wallet import Wallet


async def get_or_create_wallet(
    db: AsyncSession,
    user_id: int,
    currency: str,
) -> Wallet:
    """Load wallet by (user_id, currency) or insert a new one. Caller must own the transaction."""
    currency = currency.upper()
    result = await db.execute(
        select(Wallet).where(
            Wallet.user_id == user_id,
            Wallet.currency == currency,
        )
    )
    wallet = result.scalar_one_or_none()
    if wallet is not None:
        return wallet
    wallet = Wallet(
        user_id=user_id,
        currency=currency,
        available=Decimal("0"),
        reserved=Decimal("0"),
    )
    db.add(wallet)
    await db.flush()
    await db.refresh(wallet)
    return wallet


async def deposit(
    db: AsyncSession,
    user_id: int,
    currency: str,
    amount: Decimal,
) -> Wallet:
    currency = currency.upper()
    await db.rollback()
    async with db.begin():
        wallet = await get_or_create_wallet(db, user_id, currency)
        new_available = wallet.available + amount
        if new_available < 0 or wallet.reserved < 0:
            raise HTTPException(status_code=400, detail="Invalid balance")
        wallet.available = new_available
        await db.flush()
        await db.refresh(wallet)
    return wallet


async def withdraw(
    db: AsyncSession,
    user_id: int,
    currency: str,
    amount: Decimal,
) -> Wallet:
    currency = currency.upper()
    await db.rollback()
    async with db.begin():
        wallet = await get_or_create_wallet(db, user_id, currency)
        if wallet.available < amount:
            raise HTTPException(status_code=400, detail="Insufficient balance")
        new_available = wallet.available - amount
        if new_available < 0 or wallet.reserved < 0:
            raise HTTPException(status_code=400, detail="Invalid balance")
        wallet.available = new_available
        await db.flush()
        await db.refresh(wallet)
    return wallet


async def get_wallets(db: AsyncSession, user_id: int) -> list[Wallet]:
    result = await db.execute(select(Wallet).where(Wallet.user_id == user_id))
    return list(result.scalars().all())


async def get_wallet(db: AsyncSession, user_id: int, currency: str) -> Wallet:
    currency = currency.upper()
    result = await db.execute(
        select(Wallet).where(
            Wallet.user_id == user_id,
            Wallet.currency == currency,
        )
    )
    wallet = result.scalar_one_or_none()
    if wallet is None:
        raise HTTPException(status_code=404, detail="Wallet not found")
    return wallet
