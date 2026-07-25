import logging

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.common.account_security_enums import (
    AccountVerificationPurpose,
)
from app.common.billing_enums import BillingProvider
from app.common.enums import (
    UserRole,
    UserStatus,
)
from app.common.exceptions import (
    ConflictException,
    ForbiddenException,
    NotFoundException,
)
from app.common.time import utc_now
from app.core.security import (
    hash_password,
    verify_password,
)
from app.models.user import User
from app.repositories.billing_customer_repository import (
    billing_customer_repository,
)
from app.repositories.user_repository import (
    user_repository,
)
from app.schemas.admin_user import (
    AdminUserCreate,
    AdminUserPasswordReset,
    AdminUserTokenAdjustment,
    AdminUserUpdate,
)
from app.schemas.user import (
    UserCreate,
    UserPasswordChange,
    UserUpdate,
)
from app.services.account_security_service import (
    account_security_service,
)
from app.services.auth_service import auth_service
from app.services.runtime_settings_service import (
    runtime_settings_service,
)
from app.services.storage_service import (
    storage_service,
)
from app.services.stripe_client_service import (
    stripe_client_service,
)
from app.services.token_service import (
    token_service,
)


logger = logging.getLogger(
    "app.user_service"
)


class UserService:
    def _credit_signup_tokens(
        self,
        db: Session,
        *,
        user: User,
    ) -> None:
        free_tokens = (
            runtime_settings_service
            .free_signup_tokens(db)
        )

        if free_tokens <= 0:
            return

        token_service.credit_tokens(
            db=db,
            user_id=user.id,
            amount=free_tokens,
            source="signup_bonus",
            description="Free signup tokens.",
        )

        db.refresh(user)

    def create_user(
        self,
        db: Session,
        user_data: UserCreate,
        *,
        requested_ip: str | None = None,
        user_agent: str | None = None,
    ) -> User:
        runtime_registration_enabled = (
            runtime_settings_service
            .registration_enabled(db)
        )

        security_settings = (
            account_security_service
            .get_or_create_settings(db)
        )

        if (
            not runtime_registration_enabled
            or not security_settings
            .registration_enabled
        ):
            raise ForbiddenException(
                "Registration is currently disabled."
            )

        normalized_email = (
            str(user_data.email)
            .strip()
            .lower()
        )

        existing_user = (
            user_repository.get_by_email(
                db,
                normalized_email,
            )
        )

        if existing_user:
            raise ConflictException(
                "A user with this email already exists."
            )

        if (
            security_settings
            .require_terms_acceptance
            and not user_data.terms_accepted
        ):
            raise ForbiddenException(
                "You must accept the terms "
                "and conditions."
            )

        if (
            security_settings
            .require_age_confirmation
            and not user_data.age_confirmed
        ):
            raise ForbiddenException(
                "You must confirm that you meet "
                "the minimum age requirement."
            )

        verification_required = (
            security_settings
            .verification_required
            and security_settings
            .verification_method
            != "disabled"
        )

        user_dict = user_data.model_dump()

        password = user_dict.pop("password")

        terms_accepted = bool(
            user_dict.pop(
                "terms_accepted",
                False,
            )
        )

        terms_version = user_dict.pop(
            "terms_version",
            None,
        )

        age_confirmed = bool(
            user_dict.pop(
                "age_confirmed",
                False,
            )
        )

        user_dict["email"] = (
            normalized_email
        )

        user_dict["hashed_password"] = (
            hash_password(password)
        )

        user_dict["auth_provider"] = "email"
        user_dict["provider_user_id"] = None
        user_dict["role"] = UserRole.USER.value
        user_dict["status"] = UserStatus.ACTIVE.value
        user_dict["is_active"] = True

        user_dict["is_verified"] = (
            not verification_required
        )

        # Campo temporal de validación anti-bot; no pertenece al modelo SQLAlchemy User.
        user_dict.pop("turnstile_token", None)
        user = user_repository.create(
            db,
            data=user_dict,
        )

        security = (
            account_security_service
            .get_or_create_user_security(
                db,
                user_id=user.id,
            )
        )

        security.terms_accepted = (
            terms_accepted
        )

        security.terms_version = (
            terms_version
        )

        security.terms_accepted_at = (
            utc_now()
            if terms_accepted
            else None
        )

        security.age_confirmed = (
            age_confirmed
        )

        security.age_confirmed_at = (
            utc_now()
            if age_confirmed
            else None
        )

        security.verification_required = (
            verification_required
        )

        if verification_required:
            security.account_status = (
                "pending_verification"
            )
            security.email_verified = False
            security.email_verified_at = None
        else:
            security.account_status = "active"
            security.email_verified = True
            security.email_verified_at = utc_now()

        db.add(security)
        db.commit()
        db.refresh(user)

        if verification_required:
            try:
                (
                    account_security_service
                    .create_challenge(
                        db,
                        email=user.email,
                        purpose=(
                            AccountVerificationPurpose
                            .REGISTRATION
                            .value
                        ),
                        requested_ip=(
                            requested_ip
                        ),
                        user_agent=user_agent,
                    )
                )
            except Exception:
                logger.exception(
                    "User was created but the "
                    "initial verification email "
                    "could not be sent.",
                    extra={
                        "user_id": user.id,
                    },
                )
        else:
            self._credit_signup_tokens(
                db,
                user=user,
            )

        db.refresh(user)

        return user

    def mark_email_verified(
        self,
        db: Session,
        *,
        email: str,
    ) -> User | None:
        normalized_email = (
            email.strip().lower()
        )

        user = (
            user_repository.get_by_email(
                db,
                normalized_email,
            )
        )

        if user is None:
            return None

        was_already_verified = bool(
            user.is_verified
        )

        user.is_verified = True

        db.add(user)
        db.commit()
        db.refresh(user)

        security = (
            account_security_service
            .get_or_create_user_security(
                db,
                user_id=user.id,
            )
        )

        security.email_verified = True

        if security.email_verified_at is None:
            security.email_verified_at = utc_now()

        security.account_status = "active"

        db.add(security)
        db.commit()

        if not was_already_verified:
            self._credit_signup_tokens(
                db,
                user=user,
            )

        db.refresh(user)

        return user

    def admin_create_user(
        self,
        db: Session,
        user_data: AdminUserCreate,
    ) -> User:
        existing_user = (
            user_repository.get_by_email(
                db,
                user_data.email,
            )
        )

        if existing_user:
            raise ConflictException(
                "A user with this email already exists."
            )

        data = user_data.model_dump()
        password = data.pop("password")

        data["email"] = (
            str(data["email"])
            .strip()
            .lower()
        )

        data["hashed_password"] = (
            hash_password(password)
        )

        data["auth_provider"] = "email"
        data["provider_user_id"] = None

        user = user_repository.create(
            db,
            data=data,
        )

        (
            account_security_service
            .get_or_create_user_security(
                db,
                user_id=user.id,
            )
        )

        return user

    def get_user_by_id(
        self,
        db: Session,
        user_id: int,
    ) -> User | None:
        return user_repository.get_by_id(
            db,
            user_id,
        )

    def get_user_by_email(
        self,
        db: Session,
        email: str,
    ) -> User | None:
        return user_repository.get_by_email(
            db,
            email,
        )

    def list_users(
        self,
        db: Session,
        *,
        skip: int = 0,
        limit: int = 50,
        include_deleted: bool = False,
    ) -> list[User]:
        return user_repository.list_users(
            db,
            skip=skip,
            limit=limit,
            include_deleted=include_deleted,
        )

    def count_users(
        self,
        db: Session,
    ) -> int:
        return user_repository.count_all(db)

    def update_user(
        self,
        db: Session,
        user: User,
        user_data: UserUpdate,
    ) -> User:
        return user_repository.update(
            db,
            db_obj=user,
            data=user_data.model_dump(
                exclude_unset=True
            ),
        )

    def change_password(
        self,
        db: Session,
        user: User,
        data: UserPasswordChange,
    ) -> None:
        if user.hashed_password is None:
            raise ForbiddenException(
                "Password change is not "
                "available for this account."
            )

        if not verify_password(
            data.current_password,
            user.hashed_password,
        ):
            raise ForbiddenException(
                "Current password is incorrect."
            )

        user.hashed_password = hash_password(
            data.new_password
        )

        db.add(user)
        db.commit()

        security = (
            account_security_service
            .get_or_create_user_security(
                db,
                user_id=user.id,
            )
        )

        security.password_changed_at = utc_now()
        security.failed_login_attempts = 0
        security.locked_until = None

        db.add(security)
        db.commit()

        auth_service.revoke_all_user_sessions(
            db,
            user_id=user.id,
        )

    def update_avatar(
        self,
        db: Session,
        user: User,
        avatar: UploadFile,
    ) -> User:
        file_obj = (
            storage_service.save_upload_file(
                db=db,
                user_id=user.id,
                file=avatar,
                folder="avatars",
            )
        )

        return user_repository.update(
            db,
            db_obj=user,
            data={
                "avatar_file_id": (
                    file_obj.id
                ),
            },
        )

    def soft_delete_own_account(
        self,
        db: Session,
        user: User,
    ) -> User:
        result = user_repository.update(
            db,
            db_obj=user,
            data={
                "is_active": False,
                "status": (
                    UserStatus.INACTIVE.value
                ),
                "deleted_at": utc_now(),
            },
        )

        security = (
            account_security_service
            .get_or_create_user_security(
                db,
                user_id=user.id,
            )
        )

        security.account_status = "deleted"

        db.add(security)
        db.commit()

        auth_service.revoke_all_user_sessions(
            db,
            user_id=user.id,
        )

        return result

    def admin_update_user(
        self,
        db: Session,
        user_id: int,
        user_data: AdminUserUpdate,
    ) -> User:
        user = self.get_user_by_id(
            db,
            user_id,
        )

        if not user:
            raise NotFoundException(
                "User not found."
            )

        update_data = user_data.model_dump(
            exclude_unset=True
        )

        if (
            "email" in update_data
            and update_data["email"]
            != user.email
        ):
            normalized_email = (
                str(update_data["email"])
                .strip()
                .lower()
            )

            existing_user = (
                user_repository.get_by_email(
                    db,
                    normalized_email,
                )
            )

            if existing_user:
                raise ConflictException(
                    "A user with this email "
                    "already exists."
                )

            update_data["email"] = (
                normalized_email
            )

            update_data["is_verified"] = False

        return user_repository.update(
            db,
            db_obj=user,
            data=update_data,
        )

    def admin_reset_password(
        self,
        db: Session,
        user_id: int,
        data: AdminUserPasswordReset,
    ) -> None:
        user = self.get_user_by_id(
            db,
            user_id,
        )

        if not user:
            raise NotFoundException(
                "User not found."
            )

        user.hashed_password = hash_password(
            data.new_password
        )

        db.add(user)
        db.commit()

        security = (
            account_security_service
            .get_or_create_user_security(
                db,
                user_id=user.id,
            )
        )

        security.password_changed_at = utc_now()
        security.failed_login_attempts = 0
        security.locked_until = None

        db.add(security)
        db.commit()

        auth_service.revoke_all_user_sessions(
            db,
            user_id=user.id,
        )

    def admin_suspend_user(
        self,
        db: Session,
        user_id: int,
    ) -> User:
        user = self.get_user_by_id(
            db,
            user_id,
        )

        if not user:
            raise NotFoundException(
                "User not found."
            )

        result = user_repository.update(
            db,
            db_obj=user,
            data={
                "is_active": False,
                "status": (
                    UserStatus.SUSPENDED.value
                ),
            },
        )

        security = (
            account_security_service
            .get_or_create_user_security(
                db,
                user_id=user.id,
            )
        )

        security.account_status = "suspended"

        db.add(security)
        db.commit()

        auth_service.revoke_all_user_sessions(
            db,
            user_id=user.id,
        )

        return result

    def admin_activate_user(
        self,
        db: Session,
        user_id: int,
    ) -> User:
        user = self.get_user_by_id(
            db,
            user_id,
        )

        if not user:
            raise NotFoundException(
                "User not found."
            )

        result = user_repository.update(
            db,
            db_obj=user,
            data={
                "is_active": True,
                "status": (
                    UserStatus.ACTIVE.value
                ),
                "deleted_at": None,
            },
        )

        security = (
            account_security_service
            .get_or_create_user_security(
                db,
                user_id=user.id,
            )
        )

        security.account_status = (
            "active"
            if security.email_verified
            else "pending_verification"
        )

        db.add(security)
        db.commit()

        return result

    def admin_soft_delete_user(
        self,
        db: Session,
        user_id: int,
    ) -> User:
        user = self.get_user_by_id(
            db,
            user_id,
        )

        if not user:
            raise NotFoundException(
                "User not found."
            )

        result = user_repository.update(
            db,
            db_obj=user,
            data={
                "is_active": False,
                "status": (
                    UserStatus.INACTIVE.value
                ),
                "deleted_at": utc_now(),
            },
        )

        security = (
            account_security_service
            .get_or_create_user_security(
                db,
                user_id=user.id,
            )
        )

        security.account_status = "deleted"

        db.add(security)
        db.commit()

        auth_service.revoke_all_user_sessions(
            db,
            user_id=user.id,
        )

        return result

    def admin_permanently_delete_user(
        self,
        db: Session,
        user_id: int,
        current_admin_id: int,
    ) -> None:
        if user_id == current_admin_id:
            raise ForbiddenException(
                "You cannot permanently delete your own account."
            )

        user = self.get_user_by_id(
            db,
            user_id,
        )

        if not user:
            raise NotFoundException(
                "User not found."
            )

        billing_customer = (
            billing_customer_repository
            .get_by_user_and_provider(
                db,
                user_id=user.id,
                provider=BillingProvider.STRIPE.value,
            )
        )

        # Stripe is an external system and cannot participate in the
        # database transaction. Clean it first and abort the local
        # deletion if any Stripe operation fails.
        if billing_customer is not None:
            (
                stripe_client_service
                .delete_customer_with_subscriptions(
                    db,
                    customer_id=(
                        billing_customer
                        .provider_customer_id
                    ),
                )
            )

        auth_service.revoke_all_user_sessions(
            db,
            user_id=user.id,
        )

        try:
            db.delete(user)
            db.commit()
        except Exception:
            db.rollback()
            raise


    def admin_adjust_user_tokens(
        self,
        db: Session,
        user_id: int,
        adjustment: AdminUserTokenAdjustment,
    ) -> User:
        user = self.get_user_by_id(
            db,
            user_id,
        )

        if not user:
            raise NotFoundException(
                "User not found."
            )

        new_balance = (
            user.token_balance
            + adjustment.amount
        )

        if new_balance < 0:
            raise ConflictException(
                "Token balance cannot "
                "be negative."
            )

        return user_repository.update(
            db,
            db_obj=user,
            data={
                "token_balance": new_balance,
            },
        )


user_service = UserService()
