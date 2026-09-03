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
from app.schemas.admin_mfa import (
    AdminMfaCodeRequest,
    AdminMfaOperationResponse,
    AdminMfaRecoveryCodesResponse,
    AdminMfaSetupResponse,
    AdminMfaStatusResponse,
    AdminMfaVerifySetupRequest,
)
from app.services.activity_service import (
    activity_service,
)
from app.services.admin_mfa_service import (
    admin_mfa_service,
)
from app.services.auth_service import (
    auth_service,
)


router = APIRouter()


@router.get(
    "/status",
    response_model=AdminMfaStatusResponse,
)
def get_admin_mfa_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(
        auth_guard
    ),
):
    return admin_mfa_service.status(
        db,
        user=current_user,
    )


@router.post(
    "/setup",
    response_model=AdminMfaSetupResponse,
)
def setup_admin_mfa(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        auth_guard
    ),
):
    result = admin_mfa_service.setup(
        db,
        user=current_user,
    )

    activity_service.create_log(
        db,
        user_id=current_user.id,
        action="admin_mfa_setup_started",
        description=(
            "Administrator started MFA setup."
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

    return result


@router.post(
    "/confirm",
    response_model=AdminMfaOperationResponse,
)
def confirm_admin_mfa_setup(
    data: AdminMfaVerifySetupRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        auth_guard
    ),
):
    result = (
        admin_mfa_service.confirm_setup(
            db,
            user=current_user,
            code=data.code,
        )
    )

    auth_service.revoke_all_user_sessions(
        db,
        user_id=current_user.id,
    )

    activity_service.create_log(
        db,
        user_id=current_user.id,
        action="admin_mfa_enabled",
        description=(
            "Administrative MFA was enabled. "
            "Existing sessions were revoked."
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

    return result


@router.post(
    "/recovery-codes/regenerate",
    response_model=(
        AdminMfaRecoveryCodesResponse
    ),
)
def regenerate_admin_mfa_recovery_codes(
    data: AdminMfaCodeRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        auth_guard
    ),
):
    result = (
        admin_mfa_service
        .regenerate_recovery_codes(
            db,
            user=current_user,
            code=data.code,
        )
    )

    activity_service.create_log(
        db,
        user_id=current_user.id,
        action=(
            "admin_mfa_recovery_codes_regenerated"
        ),
        description=(
            "Administrator regenerated "
            "MFA recovery codes."
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

    return result


@router.post(
    "/disable",
    response_model=AdminMfaOperationResponse,
)
def disable_admin_mfa(
    data: AdminMfaCodeRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        auth_guard
    ),
):
    result = admin_mfa_service.disable(
        db,
        user=current_user,
        code=data.code,
    )

    auth_service.revoke_all_user_sessions(
        db,
        user_id=current_user.id,
    )

    activity_service.create_log(
        db,
        user_id=current_user.id,
        action="admin_mfa_disabled",
        description=(
            "Administrative MFA was disabled. "
            "Existing sessions were revoked."
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

    return result