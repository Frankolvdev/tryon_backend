from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.auth_guard import auth_guard
from app.models.user import User
from app.schemas.token import (
    TokenBalanceResponse,
    TokenConsumeRequest,
    TokenPackageResponse,
    TokenTransactionResponse,
)
from app.schemas.user import UserResponse
from app.services.token_service import token_service

router = APIRouter()


@router.get("/balance", response_model=TokenBalanceResponse)
def get_my_balance(
    current_user: User = Depends(auth_guard),
):
    return TokenBalanceResponse(
        token_balance=token_service.get_balance(current_user),
    )


@router.get("/packages", response_model=list[TokenPackageResponse])
def list_token_packages(
    db: Session = Depends(get_db),
):
    return token_service.list_public_packages(db)


@router.get("/transactions", response_model=list[TokenTransactionResponse])
def list_my_transactions(
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_guard),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
):
    return token_service.get_user_transactions(
        db=db,
        user_id=current_user.id,
        skip=skip,
        limit=limit,
    )


@router.post("/consume", response_model=UserResponse)
def consume_tokens(
    data: TokenConsumeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_guard),
):
    return token_service.debit_tokens(
        db=db,
        user_id=current_user.id,
        amount=data.amount,
        source=data.source,
        reference_id=data.reference_id,
        description=data.description,
    )