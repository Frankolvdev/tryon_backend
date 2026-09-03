from fastapi import (
    APIRouter,
    Depends,
    File,
    Header,
    Request,
    status,
    UploadFile,
)
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.auth_guard import (
    auth_guard,
)
from app.common.exceptions import (
    NotFoundException,
)
from app.common.responses import (
    SuccessResponse,
)
from app.models.user import User
from app.schemas.password_recovery import (
    RevokeSessionsResponse,
)
from app.schemas.user import (
    UserCreate,
    UserPasswordChange,
    UserResponse,
    UserUpdate,
)
from app.services.activity_service import (
    activity_service,
)
from app.services.auth_service import (
    auth_service,
)
from app.services.registration_security_service import (
    registration_security_service,
)
from app.services.user_service import (
    user_service,
)


router = APIRouter()


@router.post(
    "/",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_user(
    user_data: UserCreate,
    request: Request,
    x_device_id: str | None = Header(
        default=None,
        alias="X-Device-ID",
    ),
    db: Session = Depends(get_db),
):
    client_ip = (
        request.client.host
        if request.client
        else None
    )

    user_agent = request.headers.get(
        "user-agent"
    )

    (
        registration_security_service
        .validate_before_registration(
            db,
            email=str(user_data.email),
            turnstile_token=(
                user_data.turnstile_token
            ),
            ip_address=client_ip,
            device_id=x_device_id,
        )
    )

    user = user_service.create_user(
        db,
        user_data,
        requested_ip=client_ip,
        user_agent=user_agent,
    )

    (
        registration_security_service
        .record_successful_registration(
            ip_address=client_ip,
            device_id=x_device_id,
        )
    )

    activity_service.create_log(
        db,
        user_id=user.id,
        action="user_registered",
        description=(
            "User registered with "
            "email and password."
        ),
        ip_address=client_ip,
        user_agent=user_agent,
    )

    return user


@router.get(
    "/me",
    response_model=UserResponse,
)
def get_me(
    current_user: User = Depends(
        auth_guard
    ),
):
    return current_user


@router.patch(
    "/me",
    response_model=UserResponse,
)
def update_me(
    data: UserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        auth_guard
    ),
):
    user = user_service.update_user(
        db,
        current_user,
        data,
    )

    activity_service.create_log(
        db,
        user_id=current_user.id,
        action="profile_updated",
        description=(
            "User updated own profile."
        ),
        ip_address=(
            request.client.host
            if request.client
            else None
        ),
        user_agent=request.headers.get(
            "user-agent"
        ),
    )

    return user


@router.post(
    "/me/change-password",
    response_model=SuccessResponse,
)
def change_my_password(
    data: UserPasswordChange,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        auth_guard
    ),
):
    user_service.change_password(
        db,
        current_user,
        data,
    )

    activity_service.create_log(
        db,
        user_id=current_user.id,
        action="password_changed",
        description=(
            "User changed own password "
            "and active sessions were revoked."
        ),
        ip_address=(
            request.client.host
            if request.client
            else None
        ),
        user_agent=request.headers.get(
            "user-agent"
        ),
    )

    return SuccessResponse(
        message=(
            "Password changed successfully. "
            "All active sessions were closed."
        ),
    )


@router.post(
    "/me/revoke-sessions",
    response_model=RevokeSessionsResponse,
)
def revoke_my_sessions(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        auth_guard
    ),
):
    revoked = (
        auth_service
        .revoke_all_user_sessions(
            db,
            user_id=current_user.id,
        )
    )

    activity_service.create_log(
        db,
        user_id=current_user.id,
        action="sessions_revoked",
        description=(
            "User revoked all active sessions."
        ),
        ip_address=(
            request.client.host
            if request.client
            else None
        ),
        user_agent=request.headers.get(
            "user-agent"
        ),
    )

    return RevokeSessionsResponse(
        success=True,
        revoked_sessions=revoked,
        message=(
            "All active sessions were closed."
        ),
    )


@router.post(
    "/me/avatar",
    response_model=UserResponse,
)
def upload_my_avatar(
    request: Request,
    avatar: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(
        auth_guard
    ),
):
    user = user_service.update_avatar(
        db,
        current_user,
        avatar,
    )

    activity_service.create_log(
        db,
        user_id=current_user.id,
        action="avatar_updated",
        description="User uploaded avatar.",
        ip_address=(
            request.client.host
            if request.client
            else None
        ),
        user_agent=request.headers.get(
            "user-agent"
        ),
    )

    return user


@router.delete(
    "/me",
    response_model=SuccessResponse,
)
def delete_my_account(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        auth_guard
    ),
):
    user_service.soft_delete_own_account(
        db,
        current_user,
    )

    activity_service.create_log(
        db,
        user_id=current_user.id,
        action="account_deactivated",
        description=(
            "User deactivated own account."
        ),
        ip_address=(
            request.client.host
            if request.client
            else None
        ),
        user_agent=request.headers.get(
            "user-agent"
        ),
    )

    return SuccessResponse(
        message=(
            "Account deactivated successfully."
        ),
    )


@router.get(
    "/{user_id}",
    response_model=UserResponse,
)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
):
    user = user_service.get_user_by_id(
        db,
        user_id,
    )

    if not user:
        raise NotFoundException(
            "User not found."
        )

    return user