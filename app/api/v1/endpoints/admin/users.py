from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.api.v1.guards.superadmin_guard import superadmin_guard
from app.common.responses import SuccessResponse
from app.models.user import User
from app.schemas.admin_user import (
    AdminUserCreate,
    AdminUserPasswordReset,
    AdminUserTokenAdjustment,
    AdminUserUpdate,
)
from app.schemas.session import SessionResponse
from app.schemas.user import UserResponse
from app.services.audit_service import audit_service
from app.services.auth_service import auth_service
from app.services.user_service import user_service

router = APIRouter()


def write_admin_audit(
    db: Session,
    request: Request,
    admin: User,
    *,
    action: str,
    entity_type: str,
    entity_id: str,
    description: str,
):
    audit_service.create_log(
        db,
        actor_user_id=admin.id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        description=description,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


@router.get("/users", response_model=list[UserResponse])
def list_users(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    include_deleted: bool = Query(default=False),
):
    return user_service.list_users(
        db=db,
        skip=skip,
        limit=limit,
        include_deleted=include_deleted,
    )


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user_admin(
    data: AdminUserCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    user = user_service.admin_create_user(db, data)

    write_admin_audit(
        db,
        request,
        current_admin,
        action="admin_user_created",
        entity_type="user",
        entity_id=str(user.id),
        description=f"Admin created user {user.email}.",
    )

    return user


@router.get("/users/{user_id}", response_model=UserResponse)
def get_user_by_id(
    user_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    user = user_service.get_user_by_id(db, user_id)

    if not user:
        from app.common.exceptions import NotFoundException

        raise NotFoundException("User not found.")

    return user


@router.patch("/users/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    data: AdminUserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    user = user_service.admin_update_user(db=db, user_id=user_id, user_data=data)

    write_admin_audit(
        db,
        request,
        current_admin,
        action="admin_user_updated",
        entity_type="user",
        entity_id=str(user.id),
        description=f"Admin updated user {user.email}.",
    )

    return user


@router.post("/users/{user_id}/reset-password", response_model=SuccessResponse)
def reset_user_password(
    user_id: int,
    data: AdminUserPasswordReset,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    user_service.admin_reset_password(db, user_id, data)

    write_admin_audit(
        db,
        request,
        current_admin,
        action="admin_user_password_reset",
        entity_type="user",
        entity_id=str(user_id),
        description="Admin reset user password.",
    )

    return SuccessResponse(message="Password reset successfully.")


@router.post("/users/{user_id}/suspend", response_model=UserResponse)
def suspend_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    user = user_service.admin_suspend_user(db, user_id)

    write_admin_audit(
        db,
        request,
        current_admin,
        action="admin_user_suspended",
        entity_type="user",
        entity_id=str(user.id),
        description=f"Admin suspended user {user.email}.",
    )

    return user


@router.post("/users/{user_id}/activate", response_model=UserResponse)
def activate_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    user = user_service.admin_activate_user(db, user_id)

    write_admin_audit(
        db,
        request,
        current_admin,
        action="admin_user_activated",
        entity_type="user",
        entity_id=str(user.id),
        description=f"Admin activated user {user.email}.",
    )

    return user


@router.delete("/users/{user_id}", response_model=SuccessResponse)
def delete_user_admin(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    user_service.admin_soft_delete_user(db, user_id)

    write_admin_audit(
        db,
        request,
        current_admin,
        action="admin_user_deleted",
        entity_type="user",
        entity_id=str(user_id),
        description="Admin deactivated user.",
    )

    return SuccessResponse(message="User deactivated successfully.")


@router.delete("/users/{user_id}/permanent", response_model=SuccessResponse)
def permanently_delete_user_admin(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(superadmin_guard),
):
    if current_admin.id == user_id:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot permanently delete your own account.",
        )

    user = user_service.get_user_by_id(db, user_id)
    if not user:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    deleted_email = user.email

    write_admin_audit(
        db,
        request,
        current_admin,
        action="admin_user_permanently_deleted",
        entity_type="user",
        entity_id=str(user_id),
        description=f"Superadmin permanently deleted user {deleted_email}.",
    )

    user_service.admin_permanently_delete_user(
        db=db,
        user_id=user_id,
        current_admin_id=current_admin.id,
    )

    return SuccessResponse(
        message="User and associated data permanently deleted.",
    )


@router.post("/users/{user_id}/tokens/adjust", response_model=UserResponse)
def adjust_user_tokens(
    user_id: int,
    data: AdminUserTokenAdjustment,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    user = user_service.admin_adjust_user_tokens(
        db=db,
        user_id=user_id,
        adjustment=data,
    )

    write_admin_audit(
        db,
        request,
        current_admin,
        action="admin_user_tokens_adjusted",
        entity_type="user",
        entity_id=str(user.id),
        description=f"Admin adjusted user tokens by {data.amount}.",
    )

    return user


@router.get("/users/{user_id}/sessions", response_model=list[SessionResponse])
def list_user_sessions(
    user_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return auth_service.admin_get_user_sessions(db=db, user_id=user_id)


@router.post("/sessions/{session_id}/revoke", response_model=SuccessResponse)
def revoke_session(
    session_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    auth_service.admin_revoke_session(db=db, session_id=session_id)

    write_admin_audit(
        db,
        request,
        current_admin,
        action="admin_session_revoked",
        entity_type="refresh_token",
        entity_id=str(session_id),
        description="Admin revoked user session.",
    )

    return SuccessResponse(message="Session revoked successfully.")