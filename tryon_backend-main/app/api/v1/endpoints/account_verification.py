from fastapi import (
    APIRouter,
    Depends,
    Request,
)
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.auth_guard import (
    auth_guard,
)
from app.models.user import User
from app.schemas.account_security import (
    AccountVerificationConfirmRequest,
    AccountVerificationConfirmResponse,
    AccountVerificationRequest,
    AccountVerificationRequestResponse,
    AccountVerificationStatusResponse,
)
from app.services.account_security_service import (
    account_security_service,
)


router = APIRouter()


@router.get(
    "/status",
    response_model=(
        AccountVerificationStatusResponse
    ),
)
def get_account_verification_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(
        auth_guard
    ),
):
    return (
        account_security_service
        .get_status(
            db,
            user_id=current_user.id,
        )
    )


@router.post(
    "/request",
    response_model=(
        AccountVerificationRequestResponse
    ),
)
def request_account_verification(
    data: AccountVerificationRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    client_ip = (
        request.client.host
        if request.client
        else None
    )

    _, _, response = (
        account_security_service
        .create_challenge(
            db,
            email=str(data.email),
            purpose=data.purpose,
            requested_ip=client_ip,
            user_agent=request.headers.get(
                "user-agent"
            ),
        )
    )

    return response


@router.post(
    "/resend",
    response_model=(
        AccountVerificationRequestResponse
    ),
)
def resend_account_verification(
    data: AccountVerificationRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    client_ip = (
        request.client.host
        if request.client
        else None
    )

    _, _, response = (
        account_security_service
        .create_challenge(
            db,
            email=str(data.email),
            purpose=data.purpose,
            requested_ip=client_ip,
            user_agent=request.headers.get(
                "user-agent"
            ),
        )
    )

    return response


@router.post(
    "/confirm",
    response_model=(
        AccountVerificationConfirmResponse
    ),
)
def confirm_account_verification(
    data: AccountVerificationConfirmRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    return (
        account_security_service
        .confirm_challenge(
            db,
            email=str(data.email),
            purpose=data.purpose,
            otp=data.otp,
            token=data.token,
            requested_ip=(
                request.client.host
                if request.client
                else None
            ),
            user_agent=request.headers.get(
                "user-agent"
            ),
        )
    )