from sqlalchemy.orm import Session

from app.services.runtime_settings_service import runtime_settings_service
from app.services.system_setting_service import system_setting_service


class ConfigurationValidationService:
    def validate(self, db: Session) -> dict:
        all_settings = system_setting_service.list_settings(db)

        missing_required = []
        restart_required = []
        sensitive_configured = []

        for setting in all_settings:
            if setting.value is None and setting.default_value is None:
                missing_required.append(setting.key)

            if setting.requires_restart:
                restart_required.append(setting.key)

            if setting.is_sensitive and setting.value is not None:
                sensitive_configured.append(setting.key)

        runtime = {
            "registration_enabled": runtime_settings_service.registration_enabled(db),
            "tryon_enabled": runtime_settings_service.tryon_enabled(db),
            "footwear_tryon_enabled": runtime_settings_service.footwear_tryon_enabled(db),
            "high_quality_enabled": runtime_settings_service.high_quality_enabled(db),
            "billing_enabled": runtime_settings_service.billing_enabled(db),
            "subscriptions_enabled": runtime_settings_service.subscriptions_enabled(db),
            "runpod_enabled": runtime_settings_service.runpod_enabled(db),
            "scheduler_enabled": runtime_settings_service.scheduler_enabled(db),
            "free_signup_tokens": runtime_settings_service.free_signup_tokens(db),
            "max_upload_size_mb": runtime_settings_service.max_upload_size_mb(db),
            "storage_provider": runtime_settings_service.storage_provider(db),
            "local_storage_dir": runtime_settings_service.local_storage_dir(db),
            "frontend_base_url": runtime_settings_service.frontend_base_url(db),
        }

        return {
            "status": "ok",
            "total_settings": len(all_settings),
            "missing_required": missing_required,
            "restart_required": restart_required,
            "sensitive_configured": sensitive_configured,
            "runtime": runtime,
        }


configuration_validation_service = ConfigurationValidationService()