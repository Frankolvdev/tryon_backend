from sqlalchemy.orm import Session

from app.common.enums import PricingOperationType, QualityMode, TryOnItemType
from app.common.exceptions import NotFoundException
from app.models.pricing_rule import PricingRule
from app.repositories.pricing_rule_repository import pricing_rule_repository
from app.schemas.pricing import PricingRuleCreate, PricingRuleUpdate


class PricingService:
    def get_tryon_price(
        self,
        db: Session,
        *,
        item_type: TryOnItemType,
        quality_mode: QualityMode,
    ) -> PricingRule:
        rule = pricing_rule_repository.get_active_rule(
            db,
            operation_type=PricingOperationType.TRYON.value,
            item_type=item_type.value,
            quality_mode=quality_mode.value,
        )

        if not rule:
            raise NotFoundException("No active pricing rule found for this operation.")

        return rule

    def list_rules(self, db: Session) -> list[PricingRule]:
        return pricing_rule_repository.list_all(db)

    def create_rule(
        self,
        db: Session,
        data: PricingRuleCreate,
    ) -> PricingRule:
        return pricing_rule_repository.create(
            db,
            data=data.model_dump(),
        )

    def update_rule(
        self,
        db: Session,
        rule_id: int,
        data: PricingRuleUpdate,
    ) -> PricingRule:
        rule = pricing_rule_repository.get_by_id(db, rule_id)

        if not rule:
            raise NotFoundException("Pricing rule not found.")

        return pricing_rule_repository.update(
            db,
            db_obj=rule,
            data=data.model_dump(exclude_unset=True),
        )


pricing_service = PricingService()