"""Wallet endpoints: list balances, deposit/withdraw flows, and addresses."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db
from app.models.user import User
from app.models.wallet import Wallet
from app.schemas.wallet import DepositRequest, WalletResponse, WithdrawRequest
from app.services import wallet_service

router = APIRouter()


@router.post("/deposit", response_model=WalletResponse)
async def deposit(
    body: DepositRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> Wallet:
    return await wallet_service.deposit(
        db,
        current_user.id,
        body.currency,
        body.amount,
    )


@router.post("/withdraw", response_model=WalletResponse)
async def withdraw(
    body: WithdrawRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> Wallet:
    return await wallet_service.withdraw(
        db,
        current_user.id,
        body.currency,
        body.amount,
    )


@router.get("", response_model=list[WalletResponse])
async def list_wallets(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[Wallet]:
    return await wallet_service.get_wallets(db, current_user.id)


@router.get("/{currency}", response_model=WalletResponse)
async def get_wallet_by_currency(
    currency: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> Wallet:
    return await wallet_service.get_wallet(db, current_user.id, currency)
