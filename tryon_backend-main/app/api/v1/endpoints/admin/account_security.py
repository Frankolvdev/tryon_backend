from fastapi import (
    APIRouter,
    Depends,
    Query,
    Request,
)
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import (
    admin_guard,
)
from app.models.user import User
from app.schemas.account_security import (
    AccountSecuritySettingsResponse,
    AccountSecuritySettingsUpdate,
    AccountVerificationChallengeListResponse,
    AccountVerificationRequestResponse,
    AdminAccountVerificationResponse,
    AdminCancelVerificationRequest,
    AdminResendVerificationRequest,
    AdminVerifyUserRequest,
    UnverifiedAccountListResponse,
    UnverifiedCleanupRequest,
    UnverifiedCleanupResponse,
)
from app.services.account_security_service import (
    account_security_service,
)
from app.services.audit_entry_service import (
    audit_entry_service,
)
from app.services.unverified_account_cleanup_service import (
    unverified_account_cleanup_service,
)


router = APIRouter()


@router.get(
    "/account-security/settings",
    response_model=(
        AccountSecuritySettingsResponse
    ),
)
def get_account_security_settings(
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    return (
        account_security_service
        .get_settings_response(db)
    )


@router.put(
    "/account-security/settings",
    response_model=(
        AccountSecuritySettingsResponse
    ),
)
def update_account_security_settings(
    data: AccountSecuritySettingsUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    before = (
        account_security_service
        .get_settings_response(db)
    )

    result = (
        account_security_service
        .update_settings(
            db,
            data=data,
        )
    )

    audit_entry_service.safe_record(
        db,
        action="update",
        entity_type=(
            "account_security_settings"
        ),
        entity_id=result.id,
        actor=current_admin,
        before=before,
        after=result,
        request=request,
        metadata={
            "module": "account_security",
            "verification_method": (
                result.verification_method
            ),
            "admin_mfa_required": (
                result.admin_mfa_required
            ),
        },
        is_restorable=True,
    )

    return result


@router.get(
    "/account-security/challenges",
    response_model=(
        AccountVerificationChallengeListResponse
    ),
)
def list_account_verification_challenges(
    user_id: int | None = Query(
        default=None,
    ),
    email: str | None = Query(
        default=None,
    ),
    purpose: str | None = Query(
        default=None,
    ),
    status: str | None = Query(
        default=None,
    ),
    skip: int = Query(
        default=0,
        ge=0,
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=1000,
    ),
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    return (
        account_security_service
        .list_challenges(
            db,
            user_id=user_id,
            email=email,
            purpose=purpose,
            status=status,
            skip=skip,
            limit=limit,
        )
    )


@router.post(
    "/account-security/users/{user_id}/verify",
    response_model=(
        AdminAccountVerificationResponse
    ),
)
def manually_verify_user(
    user_id: int,
    data: AdminVerifyUserRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    result = (
        account_security_service
        .admin_verify_user(
            db,
            user_id=user_id,
        )
    )

    audit_entry_service.safe_record(
        db,
        action="verify",
        entity_type="user",
        entity_id=user_id,
        actor=current_admin,
        before=None,
        after=result,
        request=request,
        metadata={
            "module": "account_security",
            "reason": data.reason,
            "manual_verification": True,
        },
    )

    return result


@router.post(
    "/account-security/users/{user_id}/resend",
    response_model=(
        AccountVerificationRequestResponse
    ),
)
def resend_user_verification(
    user_id: int,
    data: AdminResendVerificationRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    result = (
        account_security_service
        .admin_resend_verification(
            db,
            user_id=user_id,
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

    audit_entry_service.safe_record(
        db,
        action="resend",
        entity_type=(
            "account_verification"
        ),
        entity_id=user_id,
        actor=current_admin,
        before=None,
        after=result,
        request=request,
        metadata={
            "module": "account_security",
            "reason": data.reason,
        },
    )

    return result


@router.post(
    "/account-security/users/{user_id}/cancel",
    response_model=(
        AdminAccountVerificationResponse
    ),
)
def cancel_user_verification(
    user_id: int,
    data: AdminCancelVerificationRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    result = (
        account_security_service
        .admin_cancel_verification(
            db,
            user_id=user_id,
        )
    )

    audit_entry_service.safe_record(
        db,
        action="cancel",
        entity_type=(
            "account_verification"
        ),
        entity_id=user_id,
        actor=current_admin,
        before=None,
        after=result,
        request=request,
        metadata={
            "module": "account_security",
            "reason": data.reason,
        },
    )

    return result


@router.get(
    "/account-security/unverified-accounts",
    response_model=(
        UnverifiedAccountListResponse
    ),
)
def list_unverified_accounts(
    eligible_only: bool = Query(
        default=False,
    ),
    skip: int = Query(
        default=0,
        ge=0,
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=1000,
    ),
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    return (
        unverified_account_cleanup_service
        .list_unverified_accounts(
            db,
            eligible_only=eligible_only,
            skip=skip,
            limit=limit,
        )
    )


@router.post(
    "/account-security/unverified-accounts/cleanup",
    response_model=(
        UnverifiedCleanupResponse
    ),
)
def cleanup_unverified_accounts(
    data: UnverifiedCleanupRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    result = (
        unverified_account_cleanup_service
        .cleanup(
            db,
            dry_run=data.dry_run,
            limit=data.limit,
        )
    )

    audit_entry_service.safe_record(
        db,
        action=(
            "simulate_cleanup"
            if data.dry_run
            else "cleanup"
        ),
        entity_type=(
            "unverified_accounts"
        ),
        entity_id=None,
        actor=current_admin,
        before=None,
        after=result,
        request=request,
        metadata={
            "module": "account_security",
            "dry_run": data.dry_run,
            "limit": data.limit,
            "eligible": result.eligible,
            "deactivated": (
                result.deactivated
            ),
        },
    )

    return result