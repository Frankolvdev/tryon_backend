from sqlalchemy.orm import Session

from app.common.enums import SettingCategory, SettingValueType
from app.repositories.system_setting_repository import system_setting_repository
from app.schemas.system_setting import SystemSettingCreate
from app.services.system_setting_service import system_setting_service


class DefaultSettingsService:
    def _create_if_missing(
        self,
        db: Session,
        data: SystemSettingCreate,
    ) -> None:
        existing = system_setting_repository.get_by_key(db, data.key)

        if existing:
            return

        system_setting_service.create_setting(
            db=db,
            data=data,
        )

    def seed_defaults(self, db: Session) -> dict:
        defaults = [
            # GENERAL
            SystemSettingCreate(
                category=SettingCategory.GENERAL,
                key="app_name",
                label="Application Name",
                description="Public application name.",
                value_type=SettingValueType.STRING,
                value="AI Virtual Try-On Platform",
                default_value="AI Virtual Try-On Platform",
                is_public=True,
                sort_order=10,
            ),
            SystemSettingCreate(
                category=SettingCategory.GENERAL,
                key="support_email",
                label="Support Email",
                description="Main support contact email.",
                value_type=SettingValueType.STRING,
                value="support@example.com",
                default_value="support@example.com",
                is_public=True,
                sort_order=30,
            ),

            # AUTH
            SystemSettingCreate(
                category=SettingCategory.AUTH,
                key="registration_enabled",
                label="Registration Enabled",
                description="Allow new users to register.",
                value_type=SettingValueType.BOOLEAN,
                value=True,
                default_value=True,
                is_public=True,
                sort_order=10,
            ),
            SystemSettingCreate(
                category=SettingCategory.AUTH,
                key="email_login_enabled",
                label="Email Login Enabled",
                description="Allow users to log in with email and password.",
                value_type=SettingValueType.BOOLEAN,
                value=True,
                default_value=True,
                is_public=True,
                sort_order=20,
            ),
            SystemSettingCreate(
                category=SettingCategory.AUTH,
                key="social_login_enabled",
                label="Social Login Enabled",
                description="Global switch for social login providers.",
                value_type=SettingValueType.BOOLEAN,
                value=False,
                default_value=False,
                is_public=True,
                sort_order=30,
            ),

            # JWT
            SystemSettingCreate(
                category=SettingCategory.JWT,
                key="access_token_expire_minutes",
                label="Access Token Expiration Minutes",
                description="Access token lifetime in minutes.",
                value_type=SettingValueType.INTEGER,
                value=60,
                default_value=60,
                is_public=False,
                requires_restart=True,
                sort_order=10,
            ),
            SystemSettingCreate(
                category=SettingCategory.JWT,
                key="refresh_token_expire_days",
                label="Refresh Token Expiration Days",
                description="Refresh token lifetime in days.",
                value_type=SettingValueType.INTEGER,
                value=30,
                default_value=30,
                is_public=False,
                requires_restart=True,
                sort_order=20,
            ),

            # STORAGE
            SystemSettingCreate(
                category=SettingCategory.STORAGE,
                key="storage_provider",
                label="Storage Provider",
                description="Current storage provider.",
                value_type=SettingValueType.STRING,
                value="local",
                default_value="local",
                is_public=False,
                requires_restart=True,
                sort_order=10,
            ),
            SystemSettingCreate(
                category=SettingCategory.STORAGE,
                key="local_storage_dir",
                label="Local Storage Directory",
                description="Local storage path used during development.",
                value_type=SettingValueType.STRING,
                value="storage/local",
                default_value="storage/local",
                is_public=False,
                requires_restart=True,
                sort_order=20,
            ),
            SystemSettingCreate(
                category=SettingCategory.STORAGE,
                key="max_upload_size_mb",
                label="Max Upload Size MB",
                description="Maximum upload size in megabytes.",
                value_type=SettingValueType.INTEGER,
                value=25,
                default_value=25,
                is_public=True,
                sort_order=30,
            ),

            # COMMERCIAL ECONOMY
            SystemSettingCreate(
                category=SettingCategory.PRICING,
                key="commercial_token_value_usd",
                label="Value of 1 Token (USD)",
                description="Single global USD value used to calculate all commercial token prices.",
                value_type=SettingValueType.FLOAT,
                value=0.10,
                default_value=0.10,
                is_public=True,
                sort_order=10,
            ),
            SystemSettingCreate(
                category=SettingCategory.PRICING,
                key="commercial_operational_reserve_per_token_usd",
                label="Operational reserve per token (USD)",
                description="Additional commercial amount protected for domains, hosting, email and other operating expenses. Never changes AI token-cost math.",
                value_type=SettingValueType.FLOAT,
                value=0.0,
                default_value=0.0,
                is_public=False,
                sort_order=15,
            ),


            SystemSettingCreate(
                category=SettingCategory.PRICING,
                key="commercial_execution_billing_policy",
                label="Execution Billing Policy",
                description="Controls infrastructure and profit charges by execution outcome.",
                value_type=SettingValueType.JSON,
                value={
                    "completed": {"charge_infrastructure": True, "apply_profit": True},
                    "cancelled": {"charge_infrastructure": True, "apply_profit": False},
                    "failed_workflow_or_user": {"charge_infrastructure": True, "apply_profit": False},
                    "failed_platform_or_provider": {"charge_infrastructure": False, "apply_profit": False},
                },
                default_value={
                    "completed": {"charge_infrastructure": True, "apply_profit": True},
                    "cancelled": {"charge_infrastructure": True, "apply_profit": False},
                    "failed_workflow_or_user": {"charge_infrastructure": True, "apply_profit": False},
                    "failed_platform_or_provider": {"charge_infrastructure": False, "apply_profit": False},
                },
                is_public=False,
                sort_order=30,
            ),

            # SIMULATED AI ENGINE
            SystemSettingCreate(category=SettingCategory.SYSTEM, key="ai_execution_mode", label="AI Execution Mode", description="Select simulated, ComfyUI local, RunPod serverless or automatic routing.", value_type=SettingValueType.STRING, value="simulated", default_value="simulated", is_public=False, sort_order=210),
            SystemSettingCreate(category=SettingCategory.SYSTEM, key="simulated_engine_enabled", label="Simulated Engine Enabled", description="Enable the no-GPU simulated execution engine.", value_type=SettingValueType.BOOLEAN, value=True, default_value=True, is_public=False, sort_order=220),
            SystemSettingCreate(category=SettingCategory.SYSTEM, key="simulated_delay_seconds", label="Simulated Delay Seconds", description="Artificial delay for simulated jobs.", value_type=SettingValueType.FLOAT, value=0.5, default_value=0.5, is_public=False, sort_order=230),
            SystemSettingCreate(category=SettingCategory.SYSTEM, key="simulated_failure_rate_percent", label="Simulated Failure Rate", description="Percentage of simulated jobs that fail intentionally.", value_type=SettingValueType.FLOAT, value=0.0, default_value=0.0, is_public=False, sort_order=240),
            SystemSettingCreate(category=SettingCategory.SYSTEM, key="simulated_copy_person_image_as_result", label="Copy Person Image as Result", description="Create a local result file for successful simulated jobs.", value_type=SettingValueType.BOOLEAN, value=True, default_value=True, is_public=False, sort_order=250),

            # RUNPOD
            SystemSettingCreate(
                category=SettingCategory.RUNPOD,
                key="runpod_enabled",
                label="RunPod Enabled",
                description="Enable real RunPod Serverless execution.",
                value_type=SettingValueType.BOOLEAN,
                value=False,
                default_value=False,
                is_public=False,
                sort_order=10,
            ),
            SystemSettingCreate(
                category=SettingCategory.RUNPOD,
                key="runpod_api_key",
                label="RunPod API Key",
                description="RunPod API key.",
                value_type=SettingValueType.PASSWORD,
                value=None,
                default_value=None,
                is_public=False,
                is_sensitive=True,
                requires_restart=True,
                sort_order=20,
            ),
            SystemSettingCreate(
                category=SettingCategory.RUNPOD,
                key="runpod_default_endpoint_id",
                label="RunPod Default Endpoint ID",
                description="Default RunPod Serverless endpoint ID.",
                value_type=SettingValueType.STRING,
                value=None,
                default_value=None,
                is_public=False,
                sort_order=30,
            ),
            SystemSettingCreate(
                category=SettingCategory.RUNPOD,
                key="runpod_min_workers",
                label="RunPod Min Workers",
                description="Recommended minimum workers.",
                value_type=SettingValueType.INTEGER,
                value=0,
                default_value=0,
                is_public=False,
                sort_order=40,
            ),
            SystemSettingCreate(
                category=SettingCategory.RUNPOD,
                key="runpod_max_workers",
                label="RunPod Max Workers",
                description="Recommended maximum workers.",
                value_type=SettingValueType.INTEGER,
                value=3,
                default_value=3,
                is_public=False,
                sort_order=50,
            ),

            # AI
            SystemSettingCreate(
                category=SettingCategory.AI,
                key="tryon_enabled",
                label="Try-On Enabled",
                description="Global switch for try-on generation.",
                value_type=SettingValueType.BOOLEAN,
                value=True,
                default_value=True,
                is_public=True,
                sort_order=10,
            ),
            SystemSettingCreate(
                category=SettingCategory.AI,
                key="footwear_tryon_enabled",
                label="Footwear Try-On Enabled",
                description="Enable footwear try-on.",
                value_type=SettingValueType.BOOLEAN,
                value=True,
                default_value=True,
                is_public=True,
                sort_order=20,
            ),
            SystemSettingCreate(
                category=SettingCategory.AI,
                key="high_quality_enabled",
                label="High Quality Mode Enabled",
                description="Enable high quality AI mode.",
                value_type=SettingValueType.BOOLEAN,
                value=True,
                default_value=True,
                is_public=True,
                sort_order=30,
            ),

            # TOKENS
            SystemSettingCreate(
                category=SettingCategory.TOKENS,
                key="free_signup_tokens",
                label="Free Signup Tokens",
                description="Tokens granted to new users at signup.",
                value_type=SettingValueType.INTEGER,
                value=0,
                default_value=0,
                is_public=True,
                sort_order=10,
            ),
            SystemSettingCreate(
                category=SettingCategory.TOKENS,
                key="promotional_signup_enabled",
                label="Promotional Signup Credits Enabled",
                description="Grant signup tokens only when backed by promotional provider credit.",
                value_type=SettingValueType.BOOLEAN,
                value=False,
                default_value=False,
                is_public=False,
                sort_order=11,
            ),
            SystemSettingCreate(
                category=SettingCategory.TOKENS,
                key="promotional_signup_provider",
                label="Promotional Signup Provider",
                description="Provider whose promotional credit backs signup tokens.",
                value_type=SettingValueType.STRING,
                value="general",
                default_value="general",
                is_public=False,
                sort_order=13,
            ),
            SystemSettingCreate(
                category=SettingCategory.TOKENS,
                key="promotional_allow_pending_settlement",
                label="Allow Promotional Tokens For Pending Debt",
                description="Allow promotional tokens to unlock generations that were already pending.",
                value_type=SettingValueType.BOOLEAN,
                value=False,
                default_value=False,
                is_public=False,
                sort_order=14,
            ),
            SystemSettingCreate(
                category=SettingCategory.TOKENS,
                key="minimum_token_purchase",
                label="Minimum Token Purchase",
                description="Minimum token amount for purchase.",
                value_type=SettingValueType.INTEGER,
                value=100,
                default_value=100,
                is_public=True,
                sort_order=20,
            ),

            # BILLING
            SystemSettingCreate(
                category=SettingCategory.BILLING,
                key="billing_enabled",
                label="Billing Enabled",
                description="Enable paid purchases and subscriptions.",
                value_type=SettingValueType.BOOLEAN,
                value=False,
                default_value=False,
                is_public=True,
                sort_order=10,
            ),

            # SUBSCRIPTIONS
            SystemSettingCreate(
                category=SettingCategory.SUBSCRIPTIONS,
                key="subscriptions_enabled",
                label="Subscriptions Enabled",
                description="Enable subscription plans.",
                value_type=SettingValueType.BOOLEAN,
                value=False,
                default_value=False,
                is_public=True,
                sort_order=10,
            ),

            # PRICING

            # SCHEDULER
            SystemSettingCreate(
                category=SettingCategory.SCHEDULER,
                key="scheduler_enabled",
                label="Scheduler Enabled",
                description="Enable scheduled jobs.",
                value_type=SettingValueType.BOOLEAN,
                value=True,
                default_value=True,
                is_public=False,
                sort_order=10,
            ),

            # MAINTENANCE
            SystemSettingCreate(
                category=SettingCategory.MAINTENANCE,
                key="maintenance_mode",
                label="Maintenance Mode",
                description="Global maintenance mode switch.",
                value_type=SettingValueType.BOOLEAN,
                value=False,
                default_value=False,
                is_public=True,
                sort_order=10,
            ),

            # FRONTEND
            SystemSettingCreate(
                category=SettingCategory.FRONTEND,
                key="generation_loading_progress_mode",
                label="Generation loading progress mode",
                description="Controls generation loaders only: use Backend-reported progress or the elapsed-time/ETA visualization. Upload progress and other loaders are unaffected.",
                value_type=SettingValueType.STRING,
                value="backend",
                default_value="backend",
                is_public=True,
                sort_order=5,
            ),
            SystemSettingCreate(
                category=SettingCategory.FRONTEND,
                key="frontend_base_url",
                label="Frontend Base URL",
                description="Public frontend URL.",
                value_type=SettingValueType.STRING,
                value="http://localhost:3000",
                default_value="http://localhost:3000",
                is_public=True,
                sort_order=10,
            ),
        ]

        created = 0
        skipped = 0

        for setting in defaults:
            existing = system_setting_repository.get_by_key(db, setting.key)

            if existing:
                skipped += 1
                continue

            self._create_if_missing(db, setting)
            created += 1

        return {
            "created": created,
            "skipped": skipped,
            "total": len(defaults),
        }


default_settings_service = DefaultSettingsService()