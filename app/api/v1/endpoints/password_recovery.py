from fastapi import (
    APIRouter,
    Depends,
    Request,
)
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.schemas.password_recovery import (
    PasswordRecoveryConfirmRequest,
    PasswordRecoveryConfirmResponse,
    PasswordRecoveryRequest,
    PasswordRecoveryRequestResponse,
)
from app.services.password_recovery_service import (
    password_recovery_service,
)


router = APIRouter()


@router.post(
    "/request",
    response_model=(
        PasswordRecoveryRequestResponse
    ),
)
def request_password_recovery(
    data: PasswordRecoveryRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    return (
        password_recovery_service
        .request_recovery(
            db,
            email=str(data.email),
            requested_ip=(
                request.client.host
                if request.client
                else None
            ),
            user_agent=(
                request.headers.get(
                    "user-agent"
                )
            ),
        )
    )


@router.post(
    "/confirm",
    response_model=(
        PasswordRecoveryConfirmResponse
    ),
)
def confirm_password_recovery(
    data: PasswordRecoveryConfirmRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    return (
        password_recovery_service
        .confirm_recovery(
            db,
            email=str(data.email),
            otp=data.otp,
            token=data.token,
            new_password=(
                data.new_password
            ),
            requested_ip=(
                request.client.host
                if request.client
                else None
            ),
            user_agent=(
                request.headers.get(
                    "user-agent"
                )
            ),
        )
    )