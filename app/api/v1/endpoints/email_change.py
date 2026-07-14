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
from app.schemas.email_change import (
    EmailChangeCancelResponse,
    EmailChangeConfirmRequest,
    EmailChangeConfirmResponse,
    EmailChangeCreate,
    EmailChangeRequestResponse,
)
from app.services.email_change_service import (
    email_change_service,
)


router = APIRouter()


@router.post(
    "/request",
    response_model=(
        EmailChangeRequestResponse
    ),
)
def request_email_change(
    data: EmailChangeCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        auth_guard
    ),
):
    return email_change_service.request_change(
        db,
        user=current_user,
        new_email=str(data.new_email),
        current_password=(
            data.current_password
        ),
        requested_ip=(
            request.client.host
            if request.client
            else None
        ),
        user_agent=request.headers.get(
            "user-agent"
        ),
    )


@router.post(
    "/resend",
    response_model=(
        EmailChangeRequestResponse
    ),
)
def resend_email_change(
    data: EmailChangeCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        auth_guard
    ),
):
    return email_change_service.request_change(
        db,
        user=current_user,
        new_email=str(data.new_email),
        current_password=(
            data.current_password
        ),
        requested_ip=(
            request.client.host
            if request.client
            else None
        ),
        user_agent=request.headers.get(
            "user-agent"
        ),
    )


@router.post(
    "/confirm",
    response_model=(
        EmailChangeConfirmResponse
    ),
)
def confirm_email_change(
    data: EmailChangeConfirmRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        auth_guard
    ),
):
    return email_change_service.confirm_change(
        db,
        user=current_user,
        new_email=str(data.new_email),
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


@router.delete(
    "/pending",
    response_model=(
        EmailChangeCancelResponse
    ),
)
def cancel_pending_email_change(
    db: Session = Depends(get_db),
    current_user: User = Depends(
        auth_guard
    ),
):
    return email_change_service.cancel_pending(
        db,
        user_id=current_user.id,
    )