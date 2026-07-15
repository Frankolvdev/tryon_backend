from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.enums import (
    IntegrationHealthStatus,
    IntegrationProvider,
    IntegrationStatus,
    UserRole,
    UserStatus,
)
from app.common.time import utc_now
from app.core.config import settings
from app.core.security import hash_password
from app.db.database import SessionLocal
from app.models.integration_config import IntegrationConfig
from app.models.user import User
from app.models.user_account_security import UserAccountSecurity
from app.services.integration_service import integration_service


SUPERADMIN_EMAIL = "admin@luxia.dev"
SUPERADMIN_PASSWORD = "LuxiaAdmin2026!"
SUPERADMIN_FULL_NAME = "Administrador Principal"


def get_user_by_email(
    db: Session,
    email: str,
) -> User | None:
    statement = select(User).where(
        User.email == email,
    )
    return db.scalar(statement)


def get_user_security(
    db: Session,
    user_id: int,
) -> UserAccountSecurity | None:
    statement = select(
        UserAccountSecurity,
    ).where(
        UserAccountSecurity.user_id
        == user_id,
    )
    return db.scalar(statement)


def create_superadmin(
    db: Session,
) -> User:
    user = User(
        email=SUPERADMIN_EMAIL,
        hashed_password=hash_password(
            SUPERADMIN_PASSWORD,
        ),
        full_name=SUPERADMIN_FULL_NAME,
        auth_provider="email",
        provider_user_id=None,
        role=UserRole.SUPERADMIN.value,
        status=UserStatus.ACTIVE.value,
        is_active=True,
        is_verified=True,
        is_superuser=True,
        token_balance=0,
        deleted_at=None,
    )

    db.add(user)
    db.flush()

    print(
        "[SEED] Superadmin created: "
        f"{user.email} (id={user.id})",
    )

    return user


def synchronize_superadmin(
    db: Session,
    user: User,
) -> User:
    updated_fields: list[str] = []

    if user.full_name != SUPERADMIN_FULL_NAME:
        user.full_name = (
            SUPERADMIN_FULL_NAME
        )
        updated_fields.append("full_name")

    if (
        user.role
        != UserRole.SUPERADMIN.value
    ):
        user.role = (
            UserRole.SUPERADMIN.value
        )
        updated_fields.append("role")

    if (
        user.status
        != UserStatus.ACTIVE.value
    ):
        user.status = (
            UserStatus.ACTIVE.value
        )
        updated_fields.append("status")

    if not user.is_active:
        user.is_active = True
        updated_fields.append("is_active")

    if not user.is_verified:
        user.is_verified = True
        updated_fields.append(
            "is_verified",
        )

    if not user.is_superuser:
        user.is_superuser = True
        updated_fields.append(
            "is_superuser",
        )

    if user.deleted_at is not None:
        user.deleted_at = None
        updated_fields.append(
            "deleted_at",
        )

    user.hashed_password = hash_password(
        SUPERADMIN_PASSWORD,
    )
    updated_fields.append(
        "hashed_password",
    )

    db.add(user)
    db.flush()

    if updated_fields:
        print(
            "[SEED] Superadmin synchronized: "
            f"{user.email}",
        )
        print(
            "[SEED] Updated fields: "
            + ", ".join(updated_fields),
        )
    else:
        print(
            "[SEED] Superadmin already configured.",
        )

    return user


def synchronize_superadmin_security(
    db: Session,
    user: User,
) -> UserAccountSecurity:
    now = utc_now()

    security = get_user_security(
        db,
        user.id,
    )

    if security is None:
        security = UserAccountSecurity(
            user_id=user.id,
            account_status="active",
            email_verified=True,
            email_verified_at=now,
            verification_required=False,
            failed_login_attempts=0,
            locked_until=None,
            terms_accepted=True,
            terms_version=(
                "development-seed"
            ),
            terms_accepted_at=now,
            age_confirmed=True,
            age_confirmed_at=now,
        )

        db.add(security)
        db.flush()

        print(
            "[SEED] Superadmin account "
            "security created.",
        )

        return security

    updated_fields: list[str] = []

    if (
        security.account_status
        != "active"
    ):
        security.account_status = "active"
        updated_fields.append(
            "account_status",
        )

    if not security.email_verified:
        security.email_verified = True
        updated_fields.append(
            "email_verified",
        )

    if (
        security.email_verified_at
        is None
    ):
        security.email_verified_at = now
        updated_fields.append(
            "email_verified_at",
        )

    if security.verification_required:
        security.verification_required = (
            False
        )
        updated_fields.append(
            "verification_required",
        )

    if (
        security.failed_login_attempts
        != 0
    ):
        security.failed_login_attempts = 0
        updated_fields.append(
            "failed_login_attempts",
        )

    if security.locked_until is not None:
        security.locked_until = None
        updated_fields.append(
            "locked_until",
        )

    if not security.terms_accepted:
        security.terms_accepted = True
        updated_fields.append(
            "terms_accepted",
        )

    if not security.terms_version:
        security.terms_version = (
            "development-seed"
        )
        updated_fields.append(
            "terms_version",
        )

    if (
        security.terms_accepted_at
        is None
    ):
        security.terms_accepted_at = now
        updated_fields.append(
            "terms_accepted_at",
        )

    if not security.age_confirmed:
        security.age_confirmed = True
        updated_fields.append(
            "age_confirmed",
        )

    if (
        security.age_confirmed_at
        is None
    ):
        security.age_confirmed_at = now
        updated_fields.append(
            "age_confirmed_at",
        )

    db.add(security)
    db.flush()

    if updated_fields:
        print(
            "[SEED] Superadmin security "
            "synchronized.",
        )
        print(
            "[SEED] Security fields updated: "
            + ", ".join(updated_fields),
        )
    else:
        print(
            "[SEED] Superadmin security "
            "already configured.",
        )

    return security


def seed_superadmin(
    db: Session,
) -> User:
    user = get_user_by_email(
        db,
        SUPERADMIN_EMAIL,
    )

    if user is None:
        user = create_superadmin(db)
    else:
        user = synchronize_superadmin(
            db,
            user,
        )

    synchronize_superadmin_security(
        db,
        user,
    )

    return user


def parse_config_json(
    value: str | None,
) -> dict:
    if not value:
        return {}

    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}

    return (
        parsed
        if isinstance(parsed, dict)
        else {}
    )


def synchronize_comfyui_integration(
    db: Session,
) -> IntegrationConfig:
    integration_service.seed_defaults(db)

    statement = select(
        IntegrationConfig,
    ).where(
        IntegrationConfig.provider
        == IntegrationProvider.COMFYUI.value,
    )

    config = db.scalar(statement)

    if config is None:
        raise RuntimeError(
            "ComfyUI integration default "
            "could not be created.",
        )

    workflows_dir = Path(
        settings.COMFYUI_WORKFLOWS_DIR,
    )
    workflows_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    current_config = parse_config_json(
        config.config_json,
    )

    current_config.update(
        {
            "mode": "local",
            "workflows_dir": str(
                workflows_dir,
            ),
            "poll_timeout_seconds": (
                settings
                .COMFYUI_POLL_TIMEOUT_SECONDS
            ),
            "poll_interval_seconds": (
                settings
                .COMFYUI_POLL_INTERVAL_SECONDS
            ),
            "person_image_node_id": (
                current_config.get(
                    "person_image_node_id",
                    "person_image",
                )
            ),
            "item_image_node_id": (
                current_config.get(
                    "item_image_node_id",
                    "item_image",
                )
            ),
            "prompt_node_id": (
                current_config.get(
                    "prompt_node_id",
                )
            ),
            "person_image_path": (
                current_config.get(
                    "person_image_path",
                    ["inputs", "image"],
                )
            ),
            "item_image_path": (
                current_config.get(
                    "item_image_path",
                    ["inputs", "image"],
                )
            ),
            "prompt_path": (
                current_config.get(
                    "prompt_path",
                    ["inputs", "text"],
                )
            ),
        }
    )

    config.name = "ComfyUI Local"
    config.status = (
        IntegrationStatus.ENABLED.value
    )
    config.is_enabled = True
    config.base_url = (
        settings.COMFYUI_BASE_URL.rstrip(
            "/",
        )
    )
    config.config_json = json.dumps(
        current_config,
        ensure_ascii=False,
    )
    config.last_health_status = (
        IntegrationHealthStatus.UNKNOWN.value
    )
    config.last_health_message = (
        "Pending health check after seed."
    )
    config.last_checked_at = None

    db.add(config)
    db.flush()

    print(
        "[SEED] ComfyUI integration "
        "synchronized.",
    )
    print(
        "[SEED] ComfyUI base URL: "
        f"{config.base_url}",
    )
    print(
        "[SEED] ComfyUI workflows dir: "
        f"{workflows_dir}",
    )

    return config


def run_seed() -> None:
    db = SessionLocal()

    try:
        print(
            "[SEED] Starting database seed",
        )

        superadmin = seed_superadmin(db)
        comfyui = (
            synchronize_comfyui_integration(
                db,
            )
        )

        db.commit()
        db.refresh(superadmin)
        db.refresh(comfyui)

        print(
            "[SEED] Database seed completed "
            "successfully",
        )
        print("")
        print("Administrative access")
        print("--------------------------------")
        print(
            f"Email: {SUPERADMIN_EMAIL}",
        )
        print(
            f"Password: {SUPERADMIN_PASSWORD}",
        )
        print(
            f"Role: {superadmin.role}",
        )
        print(
            f"Status: {superadmin.status}",
        )
        print("--------------------------------")
        print("")
        print("ComfyUI integration")
        print("--------------------------------")
        print(
            f"Enabled: {comfyui.is_enabled}",
        )
        print(
            f"Status: {comfyui.status}",
        )
        print(
            f"Base URL: {comfyui.base_url}",
        )
        print("--------------------------------")
    except Exception:
        db.rollback()
        print(
            "[SEED] Seed failed. "
            "Transaction rolled back.",
            file=sys.stderr,
        )
        raise
    finally:
        db.close()


def main() -> int:
    try:
        run_seed()
        return 0
    except Exception as error:
        print(
            f"[SEED] Error: {error}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
