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
from app.schemas.user_profile import (
    ImageProcessingConsentUpdate,
    OnboardingCompleteRequest,
    UserOnboardingStatusResponse,
    UserPrivacyResponse,
    UserPrivacyUpdate,
    UserProfileResponse,
    UserProfileUpdate,
)
from app.services.activity_service import (
    activity_service,
)
from app.services.user_profile_service import (
    user_profile_service,
)


router = APIRouter()


@router.get(
    "/me",
    response_model=UserProfileResponse,
)
def get_my_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(
        auth_guard
    ),
):
    return (
        user_profile_service.get_profile(
            db,
            user=current_user,
        )
    )


@router.put(
    "/me",
    response_model=UserProfileResponse,
)
def update_my_profile(
    data: UserProfileUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        auth_guard
    ),
):
    result = (
        user_profile_service
        .update_profile(
            db,
            user=current_user,
            data=data,
        )
    )

    activity_service.create_log(
        db,
        user_id=current_user.id,
        action="user_profile_updated",
        description=(
            "User updated profile settings."
        ),
        ip_address=(
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

    return result


@router.get(
    "/me/privacy",
    response_model=UserPrivacyResponse,
)
def get_my_privacy_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(
        auth_guard
    ),
):
    return (
        user_profile_service.get_privacy(
            db,
            user=current_user,
        )
    )


@router.put(
    "/me/privacy",
    response_model=UserPrivacyResponse,
)
def update_my_privacy_settings(
    data: UserPrivacyUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        auth_guard
    ),
):
    result = (
        user_profile_service
        .update_privacy(
            db,
            user=current_user,
            data=data,
        )
    )

    activity_service.create_log(
        db,
        user_id=current_user.id,
        action="user_privacy_updated",
        description=(
            "User updated privacy settings."
        ),
        ip_address=(
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

    return result


@router.put(
    "/me/image-processing-consent",
    response_model=UserPrivacyResponse,
)
def update_image_processing_consent(
    data: ImageProcessingConsentUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        auth_guard
    ),
):
    result = (
        user_profile_service
        .update_image_processing_consent(
            db,
            user=current_user,
            data=data,
        )
    )

    activity_service.create_log(
        db,
        user_id=current_user.id,
        action="image_processing_consent_updated",
        description=(
            "User updated image processing consent."
        ),
        ip_address=(
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

    return result


@router.get(
    "/me/onboarding",
    response_model=(
        UserOnboardingStatusResponse
    ),
)
def get_my_onboarding_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(
        auth_guard
    ),
):
    return (
        user_profile_service
        .onboarding_status(
            db,
            user=current_user,
        )
    )


@router.post(
    "/me/onboarding/complete",
    response_model=(
        UserOnboardingStatusResponse
    ),
)
def complete_my_onboarding(
    data: OnboardingCompleteRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        auth_guard
    ),
):
    result = (
        user_profile_service
        .complete_onboarding(
            db,
            user=current_user,
            data=data,
        )
    )

    activity_service.create_log(
        db,
        user_id=current_user.id,
        action="user_onboarding_completed",
        description=(
            "User completed onboarding."
        ),
        ip_address=(
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

    return result