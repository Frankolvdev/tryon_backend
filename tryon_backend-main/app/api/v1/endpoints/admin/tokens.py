from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.models.user import User
from app.schemas.token import (
    AdminTokenAdjustRequest,
    TokenPackageCreate,
    TokenPackageResponse,
    TokenPackageUpdate,
    TokenTransactionResponse,
)
from app.schemas.user import UserResponse
from app.services.token_service import token_service

router = APIRouter()


@router.get("/token-packages", response_model=list[TokenPackageResponse])
def list_token_packages_admin(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return token_service.list_admin_packages(db)


@router.post("/token-packages", response_model=TokenPackageResponse)
def create_token_package(
    data: TokenPackageCreate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return token_service.create_package(
        db=db,
        data=data,
    )


@router.patch("/token-packages/{package_id}", response_model=TokenPackageResponse)
def update_token_package(
    package_id: int,
    data: TokenPackageUpdate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return token_service.update_package(
        db=db,
        package_id=package_id,
        data=data,
    )


@router.post("/tokens/adjust", response_model=UserResponse)
def adjust_user_tokens(
    data: AdminTokenAdjustRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return token_service.admin_adjust_tokens(
        db=db,
        user_id=data.user_id,
        amount=data.amount,
        description=data.description,
    )


@router.get(
    "/users/{user_id}/token-transactions",
    response_model=list[TokenTransactionResponse],
)
def list_user_token_transactions(
    user_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
):
    return token_service.get_user_transactions(
        db=db,
        user_id=user_id,
        skip=skip,
        limit=limit,
    )

@router.get(
    "/token-transactions",
    response_model=list[TokenTransactionResponse],
)
def list_token_transactions_admin(
    user_id: int | None = Query(default=None),
    transaction_type: str | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return token_service.get_admin_transactions(
        db,
        user_id=user_id,
        transaction_type=transaction_type,
        skip=skip,
        limit=limit,
    )
