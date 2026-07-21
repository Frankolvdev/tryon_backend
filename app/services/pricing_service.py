import math

from sqlalchemy.orm import Session

from app.common.enums import PricingOperationType, QualityMode, TryOnItemType
from app.common.exceptions import NotFoundException
from app.models.pricing_rule import PricingRule
from app.repositories.pricing_rule_repository import pricing_rule_repository
from app.repositories.system_setting_repository import system_setting_repository
from app.schemas.pricing import (
    CommercialPricePreviewResponse,
    CommercialSettingsResponse,
    CommercialSettingsUpdate,
    PricingRuleCreate,
    PricingRuleResponse,
    PricingRuleUpdate,
)

TOKEN_VALUE_KEY = "commercial_token_value_usd"
CURRENCY_KEY = "commercial_currency"
DEFAULT_TOKEN_VALUE_USD = 0.10
DEFAULT_CURRENCY = "USD"


class PricingService:
    def _token_value(self, db: Session) -> float:
        setting = system_setting_repository.get_by_key(db, TOKEN_VALUE_KEY)
        value = setting.value_float if setting else DEFAULT_TOKEN_VALUE_USD
        return max(float(value or DEFAULT_TOKEN_VALUE_USD), 0.000001)

    def _currency(self, db: Session) -> str:
        setting = system_setting_repository.get_by_key(db, CURRENCY_KEY)
        return str(setting.value_string if setting else DEFAULT_CURRENCY).upper()

    def price_for_tokens(self, db: Session, tokens: int) -> tuple[float, str]:
        normalized_tokens = max(int(tokens), 0)
        amount = normalized_tokens * self._token_value(db)
        return round(amount, 2), self._currency(db)

    def get_commercial_settings(self, db: Session) -> CommercialSettingsResponse:
        return CommercialSettingsResponse(
            token_value_usd=self._token_value(db),
            currency=self._currency(db),
        )

    def update_commercial_settings(
        self, db: Session, data: CommercialSettingsUpdate
    ) -> CommercialSettingsResponse:
        token_setting = system_setting_repository.get_by_key(db, TOKEN_VALUE_KEY)
        currency_setting = system_setting_repository.get_by_key(db, CURRENCY_KEY)

        if not token_setting or not currency_setting:
            raise NotFoundException(
                "Commercial settings are missing. Seed default system settings first."
            )

        system_setting_repository.update(
            db, db_obj=token_setting, data={"value_float": float(data.token_value_usd)}
        )
        system_setting_repository.update(
            db, db_obj=currency_setting, data={"value_string": data.currency.upper()}
        )
        return self.get_commercial_settings(db)

    def preview(
        self,
        db: Session,
        *,
        average_execution_cost_usd: float,
        desired_profit_percent: float,
    ) -> CommercialPricePreviewResponse:
        token_value = self._token_value(db)
        target_price = average_execution_cost_usd * (1 + desired_profit_percent / 100)
        required_tokens = max(1, math.ceil(target_price / token_value))
        final_price = required_tokens * token_value
        effective_margin = (
            ((final_price - average_execution_cost_usd) / average_execution_cost_usd) * 100
            if average_execution_cost_usd > 0
            else 0.0
        )
        return CommercialPricePreviewResponse(
            average_execution_cost_usd=round(average_execution_cost_usd, 6),
            desired_profit_percent=round(desired_profit_percent, 4),
            token_value_usd=round(token_value, 6),
            currency=self._currency(db),
            final_price_usd=round(final_price, 6),
            required_tokens=required_tokens,
            effective_margin_percent=round(effective_margin, 4),
        )

    def _to_response(self, db: Session, rule: PricingRule) -> PricingRuleResponse:
        average_cost = float(rule.estimated_gpu_cost_cents or 0) / 100
        desired_profit = float(rule.margin_percent or 0)
        preview = self.preview(
            db,
            average_execution_cost_usd=average_cost,
            desired_profit_percent=desired_profit,
        )
        return PricingRuleResponse(
            id=rule.id,
            operation_type=rule.operation_type,
            item_type=rule.item_type,
            quality_mode=rule.quality_mode,
            average_execution_cost_usd=average_cost,
            desired_profit_percent=desired_profit,
            final_price_usd=preview.final_price_usd,
            required_tokens=preview.required_tokens,
            effective_margin_percent=preview.effective_margin_percent,
            token_value_usd=preview.token_value_usd,
            currency=preview.currency,
            is_active=rule.is_active,
            created_at=rule.created_at,
            updated_at=rule.updated_at,
        )

    def get_tryon_price(
        self, db: Session, *, item_type: TryOnItemType, quality_mode: QualityMode
    ) -> PricingRuleResponse:
        rule = pricing_rule_repository.get_active_rule(
            db,
            operation_type=PricingOperationType.TRYON.value,
            item_type=item_type.value,
            quality_mode=quality_mode.value,
        )
        if not rule:
            raise NotFoundException("No active pricing rule found for this operation.")
        return self._to_response(db, rule)

    def list_rules(self, db: Session) -> list[PricingRuleResponse]:
        return [self._to_response(db, rule) for rule in pricing_rule_repository.list_all(db)]

    def create_rule(self, db: Session, data: PricingRuleCreate) -> PricingRuleResponse:
        preview = self.preview(
            db,
            average_execution_cost_usd=data.average_execution_cost_usd,
            desired_profit_percent=data.desired_profit_percent,
        )
        rule = pricing_rule_repository.create(
            db,
            data={
                "operation_type": data.operation_type.value,
                "item_type": data.item_type.value,
                "quality_mode": data.quality_mode.value,
                "tokens_cost": preview.required_tokens,
                "estimated_gpu_seconds": 0,
                "estimated_gpu_cost_cents": round(data.average_execution_cost_usd * 100),
                "margin_percent": round(data.desired_profit_percent),
                "is_active": data.is_active,
            },
        )
        return self._to_response(db, rule)

    def update_rule(
        self, db: Session, rule_id: int, data: PricingRuleUpdate
    ) -> PricingRuleResponse:
        rule = pricing_rule_repository.get_by_id(db, rule_id)
        if not rule:
            raise NotFoundException("Pricing rule not found.")

        average_cost = (
            data.average_execution_cost_usd
            if data.average_execution_cost_usd is not None
            else float(rule.estimated_gpu_cost_cents or 0) / 100
        )
        desired_profit = (
            data.desired_profit_percent
            if data.desired_profit_percent is not None
            else float(rule.margin_percent or 0)
        )
        preview = self.preview(
            db,
            average_execution_cost_usd=average_cost,
            desired_profit_percent=desired_profit,
        )
        update_data = {
            "estimated_gpu_cost_cents": round(average_cost * 100),
            "margin_percent": round(desired_profit),
            "tokens_cost": preview.required_tokens,
        }
        if data.is_active is not None:
            update_data["is_active"] = data.is_active
        rule = pricing_rule_repository.update(db, db_obj=rule, data=update_data)
        return self._to_response(db, rule)

    def reprice_catalog(self, db: Session) -> dict[str, int | float | str]:
        from decimal import Decimal
        from app.repositories.subscription_plan_repository import subscription_plan_repository
        from app.repositories.token_package_repository import token_package_repository

        plans = subscription_plan_repository.list_all_filtered(db, skip=0, limit=10000)
        packages = token_package_repository.list_all(db)
        currency = self._currency(db)
        for plan in plans:
            amount, _ = self.price_for_tokens(db, plan.tokens_per_period)
            plan.price_amount = Decimal(str(amount))
            plan.currency = currency
            db.add(plan)
        for package in packages:
            amount, _ = self.price_for_tokens(db, package.tokens_amount)
            package.price_cents = int(round(amount * 100))
            package.currency = currency.lower()
            db.add(package)
        db.commit()
        return {"plans_updated": len(plans), "packages_updated": len(packages), "currency": currency, "token_value_usd": self._token_value(db)}


pricing_service = PricingService()
