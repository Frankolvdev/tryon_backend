from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.models.feature_flag import FeatureFlag
from app.models.integration_config import IntegrationConfig
from app.models.pricing_rule import PricingRule
from app.models.subscription_plan import SubscriptionPlan
from app.models.system_setting import SystemSetting
from app.models.token_package import TokenPackage
from app.models.workflow_definition import WorkflowDefinition


@dataclass(frozen=True)
class AuditRestoreEntityConfiguration:
    entity_type: str
    model: type

    mutable_fields: frozenset[str]
    protected_fields: frozenset[str]

    invalidation_method: str | None = None


class AuditRestoreRegistryService:
    COMMON_PROTECTED_FIELDS = frozenset(
        {
            "id",
            "created_at",
            "updated_at",
            "deleted_at",
            "created_by_user_id",
            "updated_by_user_id",
            "password",
            "password_hash",
            "hashed_password",
            "access_token",
            "refresh_token",
            "api_key",
            "secret",
            "secret_key",
            "client_secret",
            "private_key",
        }
    )

    def __init__(self):
        self._registry: dict[
            str,
            AuditRestoreEntityConfiguration,
        ] = {}

        self._register_defaults()

    def _configuration(
        self,
        *,
        entity_type: str,
        model: type,
        mutable_fields: set[str],
        protected_fields: set[str] | None = None,
        invalidation_method: str | None = None,
    ) -> AuditRestoreEntityConfiguration:
        return AuditRestoreEntityConfiguration(
            entity_type=entity_type,
            model=model,
            mutable_fields=frozenset(
                mutable_fields
            ),
            protected_fields=frozenset(
                protected_fields or set()
            )
            | self.COMMON_PROTECTED_FIELDS,
            invalidation_method=invalidation_method,
        )

    def _register_defaults(
        self,
    ) -> None:
        self.register(
            self._configuration(
                entity_type="workflow_definition",
                model=WorkflowDefinition,
                mutable_fields={
                    "key",
                    "name",
                    "description",
                    "version",
                    "category",
                    "workflow_json",
                    "parameter_schema_json",
                    "execution_modes_json",
                    "metadata_json",
                    "is_active",
                    "is_default",
                },
                protected_fields={
                    "version",
                },
                invalidation_method="workflows",
            )
        )

        self.register(
            self._configuration(
                entity_type="pricing_rule",
                model=PricingRule,
                mutable_fields={
                    "key",
                    "name",
                    "description",
                    "operation",
                    "execution_mode",
                    "currency",
                    "token_cost",
                    "price_minor",
                    "minimum_price_minor",
                    "gpu_cost_multiplier",
                    "margin_percentage",
                    "configuration_json",
                    "is_active",
                    "priority",
                },
                invalidation_method="pricing",
            )
        )

        self.register(
            self._configuration(
                entity_type="system_setting",
                model=SystemSetting,
                mutable_fields={
                    "key",
                    "value",
                    "value_json",
                    "value_type",
                    "description",
                    "category",
                    "is_public",
                    "is_editable",
                },
                protected_fields={
                    "key",
                },
                invalidation_method="settings",
            )
        )

        self.register(
            self._configuration(
                entity_type="feature_flag",
                model=FeatureFlag,
                mutable_fields={
                    "key",
                    "name",
                    "description",
                    "is_enabled",
                    "rollout_percentage",
                    "rules_json",
                    "metadata_json",
                },
                protected_fields={
                    "key",
                },
                invalidation_method="feature_flags",
            )
        )

        self.register(
            self._configuration(
                entity_type="integration_config",
                model=IntegrationConfig,
                mutable_fields={
                    "provider",
                    "name",
                    "is_enabled",
                    "configuration_json",
                    "metadata_json",
                    "environment",
                },
                protected_fields={
                    "provider",
                    "encrypted_credentials",
                    "credentials_json",
                    "api_key",
                    "secret",
                },
                invalidation_method="integrations",
            )
        )

        self.register(
            self._configuration(
                entity_type="subscription_plan",
                model=SubscriptionPlan,
                mutable_fields={
                    "name",
                    "description",
                    "price_minor",
                    "currency",
                    "billing_interval",
                    "included_tokens",
                    "features_json",
                    "is_active",
                    "sort_order",
                },
                invalidation_method=(
                    "subscription_plans"
                ),
            )
        )

        self.register(
            self._configuration(
                entity_type="token_package",
                model=TokenPackage,
                mutable_fields={
                    "name",
                    "description",
                    "token_amount",
                    "bonus_tokens",
                    "price_minor",
                    "currency",
                    "is_active",
                    "sort_order",
                },
                invalidation_method=(
                    "token_packages"
                ),
            )
        )

    def register(
        self,
        configuration: AuditRestoreEntityConfiguration,
    ) -> None:
        self._registry[
            configuration.entity_type
        ] = configuration

    def get(
        self,
        entity_type: str,
    ) -> AuditRestoreEntityConfiguration | None:
        return self._registry.get(
            entity_type.strip().lower()
        )

    def require(
        self,
        entity_type: str,
    ) -> AuditRestoreEntityConfiguration:
        configuration = self.get(
            entity_type
        )

        if configuration is None:
            supported = ", ".join(
                sorted(self._registry.keys())
            )

            raise ValueError(
                "Entity type is not restorable. "
                f"Supported types: {supported}."
            )

        return configuration

    def list_entity_types(
        self,
    ) -> list[str]:
        return sorted(
            self._registry.keys()
        )

    def get_entity(
        self,
        db: Session,
        *,
        entity_type: str,
        entity_id: str,
    ) -> Any | None:
        configuration = self.require(
            entity_type
        )

        try:
            normalized_id: Any = int(
                entity_id
            )
        except ValueError:
            normalized_id = entity_id

        return db.get(
            configuration.model,
            normalized_id,
        )


audit_restore_registry_service = (
    AuditRestoreRegistryService()
)