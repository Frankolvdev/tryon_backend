from zoneinfo import (
    ZoneInfo,
    ZoneInfoNotFoundError,
)

from sqlalchemy.orm import Session

from app.common.exceptions import (
    ConflictException,
    ForbiddenException,
)
from app.common.time import utc_now
from app.models.user import User
from app.models.user_profile_setting import (
    UserProfileSetting,
)
from app.repositories.i18n_repository import (
    i18n_repository,
)
from app.repositories.user_profile_repository import (
    user_profile_repository,
)
from app.schemas.user_profile import (
    ImageProcessingConsentUpdate,
    OnboardingCompleteRequest,
    UserOnboardingStatusResponse,
    UserPrivacyResponse,
    UserPrivacyUpdate,
    UserProfileResponse,
    UserProfileUpdate,
)


class UserProfileService:
    def _validate_timezone(
        self,
        timezone_name: str,
    ) -> str:
        try:
            ZoneInfo(timezone_name)

        except ZoneInfoNotFoundError as error:
            raise ConflictException(
                "Invalid IANA timezone."
            ) from error

        return timezone_name

    def _validate_locale(
        self,
        db: Session,
        *,
        locale_code: str,
    ) -> str:
        locale = (
            i18n_repository.get_locale(
                db,
                locale_code=locale_code,
            )
        )

        if (
            locale is None
            or not locale.is_active
        ):
            raise ConflictException(
                "The selected locale is not available."
            )

        return locale.code

    def get_or_create(
        self,
        db: Session,
        *,
        user: User,
    ) -> UserProfileSetting:
        profile = (
            user_profile_repository
            .get_by_user_id(
                db,
                user_id=user.id,
            )
        )

        if profile is not None:
            return profile

        profile = UserProfileSetting(
            user_id=user.id,
        )

        db.add(profile)
        db.commit()
        db.refresh(profile)

        return profile

    def _profile_completed(
        self,
        *,
        user: User,
        profile: UserProfileSetting,
    ) -> bool:
        return bool(
            user.full_name
            and profile.country_code
            and profile.timezone
            and profile.locale_code
            and profile.currency_code
        )

    def _response(
        self,
        *,
        user: User,
        profile: UserProfileSetting,
    ) -> UserProfileResponse:
        return UserProfileResponse(
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
            username=profile.username,
            biography=profile.biography,
            avatar_file_id=user.avatar_file_id,
            country_code=profile.country_code,
            timezone=profile.timezone,
            locale_code=profile.locale_code,
            currency_code=profile.currency_code,
            profile_visibility=(
                profile.profile_visibility
            ),
            gallery_visibility=(
                profile.gallery_visibility
            ),
            show_activity_status=(
                profile.show_activity_status
            ),
            allow_marketing_emails=(
                profile.allow_marketing_emails
            ),
            allow_product_updates=(
                profile.allow_product_updates
            ),
            allow_security_emails=(
                profile.allow_security_emails
            ),
            image_processing_consent=(
                profile.image_processing_consent
            ),
            image_processing_consent_at=(
                profile.image_processing_consent_at
            ),
            retain_input_images=(
                profile.retain_input_images
            ),
            retain_generated_images=(
                profile.retain_generated_images
            ),
            profile_completed=(
                profile.profile_completed
            ),
            onboarding_completed=(
                profile.onboarding_completed
            ),
            onboarding_completed_at=(
                profile.onboarding_completed_at
            ),
            is_verified=user.is_verified,
            is_active=user.is_active,
            created_at=profile.created_at,
            updated_at=profile.updated_at,
        )

    def get_profile(
        self,
        db: Session,
        *,
        user: User,
    ) -> UserProfileResponse:
        profile = self.get_or_create(
            db,
            user=user,
        )

        completed = self._profile_completed(
            user=user,
            profile=profile,
        )

        if (
            profile.profile_completed
            != completed
        ):
            profile.profile_completed = (
                completed
            )

            db.add(profile)
            db.commit()
            db.refresh(profile)

        return self._response(
            user=user,
            profile=profile,
        )

    def update_profile(
        self,
        db: Session,
        *,
        user: User,
        data: UserProfileUpdate,
    ) -> UserProfileResponse:
        profile = self.get_or_create(
            db,
            user=user,
        )

        update_data = data.model_dump(
            exclude_unset=True,
        )

        full_name = update_data.pop(
            "full_name",
            None,
        )

        if "full_name" in data.model_fields_set:
            user.full_name = full_name

        username = update_data.get(
            "username"
        )

        if username:
            existing = (
                user_profile_repository
                .get_by_username(
                    db,
                    username=username,
                )
            )

            if (
                existing is not None
                and existing.user_id
                != user.id
            ):
                raise ConflictException(
                    "This username is already in use."
                )

        timezone_name = update_data.get(
            "timezone"
        )

        if timezone_name:
            update_data["timezone"] = (
                self._validate_timezone(
                    timezone_name
                )
            )

        locale_code = update_data.get(
            "locale_code"
        )

        if locale_code:
            update_data["locale_code"] = (
                self._validate_locale(
                    db,
                    locale_code=locale_code,
                )
            )

        for field, value in (
            update_data.items()
        ):
            setattr(
                profile,
                field,
                value,
            )

        profile.profile_completed = (
            self._profile_completed(
                user=user,
                profile=profile,
            )
        )

        db.add(user)
        db.add(profile)
        db.commit()

        db.refresh(user)
        db.refresh(profile)

        return self._response(
            user=user,
            profile=profile,
        )

    def get_privacy(
        self,
        db: Session,
        *,
        user: User,
    ) -> UserPrivacyResponse:
        profile = self.get_or_create(
            db,
            user=user,
        )

        return UserPrivacyResponse(
            profile_visibility=(
                profile.profile_visibility
            ),
            gallery_visibility=(
                profile.gallery_visibility
            ),
            show_activity_status=(
                profile.show_activity_status
            ),
            allow_marketing_emails=(
                profile.allow_marketing_emails
            ),
            allow_product_updates=(
                profile.allow_product_updates
            ),
            allow_security_emails=(
                profile.allow_security_emails
            ),
            image_processing_consent=(
                profile.image_processing_consent
            ),
            image_processing_consent_at=(
                profile.image_processing_consent_at
            ),
            retain_input_images=(
                profile.retain_input_images
            ),
            retain_generated_images=(
                profile.retain_generated_images
            ),
        )

    def update_privacy(
        self,
        db: Session,
        *,
        user: User,
        data: UserPrivacyUpdate,
    ) -> UserPrivacyResponse:
        profile = self.get_or_create(
            db,
            user=user,
        )

        update_data = data.model_dump(
            exclude_unset=True,
        )

        for field, value in (
            update_data.items()
        ):
            setattr(
                profile,
                field,
                value,
            )

        db.add(profile)
        db.commit()
        db.refresh(profile)

        return self.get_privacy(
            db,
            user=user,
        )

    def update_image_processing_consent(
        self,
        db: Session,
        *,
        user: User,
        data: ImageProcessingConsentUpdate,
    ) -> UserPrivacyResponse:
        profile = self.get_or_create(
            db,
            user=user,
        )

        profile.image_processing_consent = (
            data.accepted
        )

        profile.image_processing_consent_at = (
            utc_now()
            if data.accepted
            else None
        )

        db.add(profile)
        db.commit()
        db.refresh(profile)

        return self.get_privacy(
            db,
            user=user,
        )

    def onboarding_status(
        self,
        db: Session,
        *,
        user: User,
    ) -> UserOnboardingStatusResponse:
        profile = self.get_or_create(
            db,
            user=user,
        )

        profile_completed = (
            self._profile_completed(
                user=user,
                profile=profile,
            )
        )

        missing_steps: list[str] = []

        if not user.is_verified:
            missing_steps.append(
                "verify_email"
            )

        if not profile_completed:
            missing_steps.append(
                "complete_profile"
            )

        if not profile.image_processing_consent:
            missing_steps.append(
                "accept_image_processing"
            )

        return UserOnboardingStatusResponse(
            profile_completed=(
                profile_completed
            ),
            onboarding_completed=(
                profile.onboarding_completed
            ),
            email_verified=user.is_verified,
            image_processing_consent=(
                profile.image_processing_consent
            ),
            missing_steps=missing_steps,
        )

    def complete_onboarding(
        self,
        db: Session,
        *,
        user: User,
        data: OnboardingCompleteRequest,
    ) -> UserOnboardingStatusResponse:
        profile = self.get_or_create(
            db,
            user=user,
        )

        profile.profile_completed = (
            self._profile_completed(
                user=user,
                profile=profile,
            )
        )

        if data.image_processing_consent:
            profile.image_processing_consent = (
                True
            )

            if (
                profile.image_processing_consent_at
                is None
            ):
                profile.image_processing_consent_at = (
                    utc_now()
                )

        if not user.is_verified:
            raise ForbiddenException(
                "Email verification is required "
                "before completing onboarding."
            )

        if not profile.profile_completed:
            raise ForbiddenException(
                "Complete your profile before "
                "finishing onboarding."
            )

        if not profile.image_processing_consent:
            raise ForbiddenException(
                "Image processing consent is required."
            )

        profile.onboarding_completed = True

        profile.onboarding_completed_at = (
            utc_now()
        )

        db.add(profile)
        db.commit()
        db.refresh(profile)

        return self.onboarding_status(
            db,
            user=user,
        )


user_profile_service = (
    UserProfileService()
)