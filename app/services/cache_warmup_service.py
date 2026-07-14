from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.feature_flag import FeatureFlag
from app.models.pricing_rule import PricingRule
from app.models.subscription_plan import (
    SubscriptionPlan,
)
from app.models.system_setting import SystemSetting
from app.models.token_package import TokenPackage
from app.models.workflow_definition import (
    WorkflowDefinition,
)
from app.schemas.cache_operations import (
    CacheWarmupItemResult,
    CacheWarmupRequest,
    CacheWarmupResponse,
)
from app.services.reference_data_cache_service import (
    reference_data_cache_service,
)
from app.services.workflow_definition_service import (
    workflow_definition_service,
)


class CacheWarmupService:
    def _model_to_dict(
        self,
        model,
    ) -> dict:
        return {
            column.name: getattr(
                model,
                column.name,
            )
            for column in model.__table__.columns
        }

    def _warm_model_list(
        self,
        db: Session,
        *,
        model,
        cache_name: str,
        cache_loader,
    ) -> CacheWarmupItemResult:
        try:
            items = list(
                db.execute(
                    select(model)
                ).scalars().all()
            )

            cache_loader(
                lambda: [
                    self._model_to_dict(item)
                    for item in items
                ]
            )

            return CacheWarmupItemResult(
                name=cache_name,
                success=True,
                loaded_items=len(items),
                message=(
                    f"Loaded {len(items)} "
                    f"{cache_name} item or items."
                ),
            )

        except Exception as error:
            return CacheWarmupItemResult(
                name=cache_name,
                success=False,
                loaded_items=0,
                message=str(error),
            )

    def run(
        self,
        db: Session,
        *,
        data: CacheWarmupRequest,
    ) -> CacheWarmupResponse:
        results: list[
            CacheWarmupItemResult
        ] = []

        if data.include_settings:
            results.append(
                self._warm_model_list(
                    db,
                    model=SystemSetting,
                    cache_name="settings",
                    cache_loader=lambda loader: (
                        reference_data_cache_service
                        .remember_settings(
                            key="all",
                            loader=loader,
                        )
                    ),
                )
            )

        if data.include_feature_flags:
            results.append(
                self._warm_model_list(
                    db,
                    model=FeatureFlag,
                    cache_name="feature_flags",
                    cache_loader=lambda loader: (
                        reference_data_cache_service
                        .remember_feature_flag_list(
                            scope="all",
                            loader=loader,
                        )
                    ),
                )
            )

        if data.include_pricing:
            results.append(
                self._warm_model_list(
                    db,
                    model=PricingRule,
                    cache_name="pricing",
                    cache_loader=lambda loader: (
                        reference_data_cache_service
                        .remember_pricing_list(
                            scope="all",
                            loader=loader,
                        )
                    ),
                )
            )

        if data.include_subscription_plans:
            results.append(
                self._warm_model_list(
                    db,
                    model=SubscriptionPlan,
                    cache_name="subscription_plans",
                    cache_loader=lambda loader: (
                        reference_data_cache_service
                        .remember_subscription_plan_list(
                            scope="all",
                            loader=loader,
                        )
                    ),
                )
            )

        if data.include_token_packages:
            results.append(
                self._warm_model_list(
                    db,
                    model=TokenPackage,
                    cache_name="token_packages",
                    cache_loader=lambda loader: (
                        reference_data_cache_service
                        .remember_token_package_list(
                            scope="all",
                            loader=loader,
                        )
                    ),
                )
            )

        if data.include_workflows:
            try:
                workflow_list = (
                    workflow_definition_service
                    .list_workflows(
                        db,
                        skip=0,
                        limit=500,
                    )
                )

                results.append(
                    CacheWarmupItemResult(
                        name="workflows",
                        success=True,
                        loaded_items=(
                            len(
                                workflow_list.items
                            )
                        ),
                        message=(
                            "Workflow catalog loaded "
                            "into cache."
                        ),
                    )
                )

            except Exception as error:
                results.append(
                    CacheWarmupItemResult(
                        name="workflows",
                        success=False,
                        loaded_items=0,
                        message=str(error),
                    )
                )

        failures = sum(
            1
            for item in results
            if not item.success
        )

        total_loaded_items = sum(
            item.loaded_items
            for item in results
        )

        return CacheWarmupResponse(
            success=failures == 0,
            items=results,
            total_loaded_items=(
                total_loaded_items
            ),
            failures=failures,
        )


cache_warmup_service = CacheWarmupService()