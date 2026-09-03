from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.system_setting_service import system_setting_service


class RuntimeSettingsService:
    def get(
        self,
        db: Session,
        key: str,
        default: Any | None = None,
    ) -> Any | None:
        return system_setting_service.get_value(
            db=db,
            key=key,
            default=default,
        )

    def get_bool(
        self,
        db: Session,
        key: str,
        default: bool = False,
    ) -> bool:
        value = self.get(db, key, default)

        if isinstance(value, bool):
            return value

        if isinstance(value, str):
            return value.lower() in ["true", "1", "yes", "on"]

        return bool(value)

    def get_int(
        self,
        db: Session,
        key: str,
        default: int = 0,
    ) -> int:
        value = self.get(db, key, default)

        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def get_float(
        self,
        db: Session,
        key: str,
        default: float = 0.0,
    ) -> float:
        value = self.get(db, key, default)

        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def get_string(
        self,
        db: Session,
        key: str,
        default: str = "",
    ) -> str:
        value = self.get(db, key, default)

        if value is None:
            return default

        return str(value)

    def registration_enabled(self, db: Session) -> bool:
        return self.get_bool(
            db,
            "registration_enabled",
            default=True,
        )

    def tryon_enabled(self, db: Session) -> bool:
        return self.get_bool(
            db,
            "tryon_enabled",
            default=True,
        )

    def footwear_tryon_enabled(self, db: Session) -> bool:
        return self.get_bool(
            db,
            "footwear_tryon_enabled",
            default=True,
        )

    def high_quality_enabled(self, db: Session) -> bool:
        return self.get_bool(
            db,
            "high_quality_enabled",
            default=True,
        )

    def billing_enabled(self, db: Session) -> bool:
        return self.get_bool(
            db,
            "billing_enabled",
            default=False,
        )

    def subscriptions_enabled(self, db: Session) -> bool:
        return self.get_bool(
            db,
            "subscriptions_enabled",
            default=False,
        )

    def runpod_enabled(self, db: Session) -> bool:
        return self.get_bool(
            db,
            "runpod_enabled",
            default=False,
        )

    def scheduler_enabled(self, db: Session) -> bool:
        return self.get_bool(
            db,
            "scheduler_enabled",
            default=True,
        )

    def free_signup_tokens(self, db: Session) -> int:
        return self.get_int(
            db,
            "free_signup_tokens",
            default=0,
        )

    def max_upload_size_mb(self, db: Session) -> int:
        return self.get_int(
            db,
            "max_upload_size_mb",
            default=25,
        )

    def access_token_expire_minutes(self, db: Session) -> int:
        return self.get_int(
            db,
            "access_token_expire_minutes",
            default=settings.ACCESS_TOKEN_EXPIRE_MINUTES,
        )

    def refresh_token_expire_days(self, db: Session) -> int:
        return self.get_int(
            db,
            "refresh_token_expire_days",
            default=settings.REFRESH_TOKEN_EXPIRE_DAYS,
        )

    def local_storage_dir(self, db: Session) -> str:
        return self.get_string(
            db,
            "local_storage_dir",
            default=settings.LOCAL_STORAGE_DIR,
        )

    def storage_provider(self, db: Session) -> str:
        return self.get_string(
            db,
            "storage_provider",
            default=settings.STORAGE_PROVIDER,
        )

    def runpod_api_key(self, db: Session) -> str:
        value = self.get_string(
            db,
            "runpod_api_key",
            default="",
        )

        if value == "********":
            return ""

        return value

    def runpod_default_endpoint_id(self, db: Session) -> str:
        return self.get_string(
            db,
            "runpod_default_endpoint_id",
            default="",
        )

    def frontend_base_url(self, db: Session) -> str:
        return self.get_string(
            db,
            "frontend_base_url",
            default="http://localhost:3000",
        )


runtime_settings_service = RuntimeSettingsService()