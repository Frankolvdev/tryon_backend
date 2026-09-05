from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.pricing_rule import PricingRule
from app.repositories.base import BaseRepository


class PricingRuleRepository(BaseRepository[PricingRule]):
    def __init__(self):
        super().__init__(PricingRule)

    def get_active_rule(
        self,
        db: Session,
        *,
        operation_type: str,
        item_type: str,
        quality_mode: str,
    ) -> PricingRule | None:
        statement = (
            select(PricingRule)
            .where(PricingRule.operation_type == operation_type)
            .where(PricingRule.item_type == item_type)
            .where(PricingRule.quality_mode == quality_mode)
            .where(PricingRule.is_active.is_(True))
            .order_by(PricingRule.id.desc())
        )

        return db.execute(statement).scalars().first()

    def get_for_generation_module(self, db: Session, module_id: int) -> PricingRule | None:
        # Generation modules own the assignment; pricing rules are reusable catalog
        # entries and may be referenced by any number of modules.
        from app.models.generation_module import GenerationModule

        module = db.get(GenerationModule, module_id)
        if module is None:
            return None
        pricing_rule_id = getattr(module, "pricing_rule_id", None)
        if pricing_rule_id is not None:
            return db.get(PricingRule, pricing_rule_id)

        # Transitional compatibility for databases that have not run the reusable
        # pricing-rule migration yet.
        statement = (
            select(PricingRule)
            .where(PricingRule.generation_module_id == module_id)
            .order_by(PricingRule.is_active.desc(), PricingRule.id.desc())
        )
        return db.execute(statement).scalars().first()

    def list_for_generation_module(self, db: Session, module_id: int) -> list[PricingRule]:
        rule = self.get_for_generation_module(db, module_id)
        return [rule] if rule is not None else []

    def list_all(self, db: Session) -> list[PricingRule]:
        statement = select(PricingRule).order_by(PricingRule.id.desc())
        return list(db.execute(statement).scalars().all())


pricing_rule_repository = PricingRuleRepository()