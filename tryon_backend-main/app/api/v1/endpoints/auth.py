from fastapi import (
    APIRouter,
    Depends,
    Request,
    status,
)
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.common.responses import (
    SuccessResponse,
)
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    TokenResponse,
)
from app.services.auth_service import (
    auth_service,
)


router = APIRouter()


@router.post(
    "/login",
    response_model=TokenResponse,
)
def login(
    data: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    return auth_service.login(
        db=db,
        email=str(data.email),
        password=data.password,
        mfa_code=data.mfa_code,
        user_agent=(
            request.headers.get(
                "user-agent"
            )
        ),
        ip_address=(
            request.client.host
            if request.client
            else None
        ),
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
)
def refresh_token(
    data: RefreshRequest,
    db: Session = Depends(get_db),
):
    return (
        auth_service
        .refresh_access_token(
            db=db,
            refresh_token=(
                data.refresh_token
            ),
        )
    )


@router.post(
    "/logout",
    response_model=SuccessResponse,
    status_code=status.HTTP_200_OK,
)
def logout(
    data: LogoutRequest,
    db: Session = Depends(get_db),
):
    auth_service.logout(
        db=db,
        refresh_token=(
            data.refresh_token
        ),
    )

    return SuccessResponse(
        message=(
            "Logged out successfully."
        ),
    )