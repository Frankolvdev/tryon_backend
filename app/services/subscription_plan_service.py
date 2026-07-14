import json
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy.orm import Session

from app.common.billing_enums import BillingInterval
from app.common.exceptions import ConflictException, NotFoundException
from app.models.subscription_plan import SubscriptionPlan
from app.repositories.subscription_plan_repository import (
    subscription_plan_repository,
)
from app.schemas.subscription_plan import (
    SubscriptionPlanCreate,
    SubscriptionPlanListResponse,
    SubscriptionPlanResponse,
    SubscriptionPlanSeedResponse,
    SubscriptionPlanSyncResponse,
    SubscriptionPlanUpdate,
)
from app.services.integration_service import integration_service
from app.services.stripe_client_service import stripe_client_service


class SubscriptionPlanService:
    def _serialize_json(self, value: Any) -> str:
        return json.dumps(
            value or {},
            ensure_ascii=False,
            default=str,
        )

    def _parse_list(self, value: str | None) -> list[str]:
        if not value:
            return []

        try:
            parsed = json.loads(value)

            if isinstance(parsed, list):
                return [str(item) for item in parsed]

            return []
        except json.JSONDecodeError:
            return []

    def _parse_dict(self, value: str | None) -> dict[str, Any]:
        if not value:
            return {}

        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}

    def _to_response(
        self,
        plan: SubscriptionPlan,
    ) -> SubscriptionPlanResponse:
        return SubscriptionPlanResponse(
            id=plan.id,
            key=plan.key,
            name=plan.name,
            description=plan.description,
            billing_interval=plan.billing_interval,
            currency=plan.currency,
            price_amount=plan.price_amount,
            tokens_per_period=plan.tokens_per_period,
            max_generations_per_period=plan.max_generations_per_period,
            priority=plan.priority,
            stripe_product_id=plan.stripe_product_id,
            stripe_price_id=plan.stripe_price_id,
            stripe_configured=bool(
                plan.stripe_product_id and plan.stripe_price_id
            ),
            features=self._parse_list(plan.features_json),
            metadata=self._parse_dict(plan.metadata_json),
            is_public=plan.is_public,
            is_active=plan.is_active,
            sort_order=plan.sort_order,
            created_at=plan.created_at,
            updated_at=plan.updated_at,
        )

    def get_plan(
        self,
        db: Session,
        plan_id: int,
    ) -> SubscriptionPlan:
        plan = subscription_plan_repository.get_by_id(db, plan_id)

        if not plan:
            raise NotFoundException("Subscription plan not found.")

        return plan

    def get_plan_by_key(
        self,
        db: Session,
        key: str,
        *,
        require_active: bool = False,
    ) -> SubscriptionPlan:
        plan = subscription_plan_repository.get_by_key(db, key)

        if not plan:
            raise NotFoundException("Subscription plan not found.")

        if require_active and not plan.is_active:
            raise ConflictException("Subscription plan is not active.")

        return plan

    def get_response(
        self,
        db: Session,
        plan_id: int,
    ) -> SubscriptionPlanResponse:
        return self._to_response(self.get_plan(db, plan_id))

    def list_admin_plans(
        self,
        db: Session,
        *,
        search: str | None = None,
        billing_interval: BillingInterval | None = None,
        is_active: bool | None = None,
        is_public: bool | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> SubscriptionPlanListResponse:
        interval_value = (
            billing_interval.value
            if billing_interval is not None
            else None
        )

        items = subscription_plan_repository.list_all_filtered(
            db,
            search=search,
            billing_interval=interval_value,
            is_active=is_active,
            is_public=is_public,
            skip=skip,
            limit=limit,
        )

        total = subscription_plan_repository.count_filtered(
            db,
            search=search,
            billing_interval=interval_value,
            is_active=is_active,
            is_public=is_public,
        )

        return SubscriptionPlanListResponse(
            items=[self._to_response(item) for item in items],
            total=total,
            skip=skip,
            limit=limit,
        )

    def list_public_plans(
        self,
        db: Session,
        *,
        billing_interval: BillingInterval | None = None,
    ) -> list[SubscriptionPlanResponse]:
        items = subscription_plan_repository.list_public_active(
            db,
            billing_interval=(
                billing_interval.value
                if billing_interval is not None
                else None
            ),
        )

        return [self._to_response(item) for item in items]

    def create_plan(
        self,
        db: Session,
        *,
        data: SubscriptionPlanCreate,
    ) -> SubscriptionPlanResponse:
        existing = subscription_plan_repository.get_by_key(
            db,
            data.key,
        )

        if existing:
            raise ConflictException(
                "Subscription plan key already exists."
            )

        plan = subscription_plan_repository.create(
            db,
            data={
                "key": data.key,
                "name": data.name,
                "description": data.description,
                "billing_interval": data.billing_interval.value,
                "currency": data.currency.upper(),
                "price_amount": data.price_amount,
                "tokens_per_period": data.tokens_per_period,
                "max_generations_per_period": (
                    data.max_generations_per_period
                ),
                "priority": data.priority,
                "features_json": self._serialize_json(data.features),
                "metadata_json": self._serialize_json(data.metadata),
                "is_public": data.is_public,
                "is_active": data.is_active,
                "sort_order": data.sort_order,
            },
        )

        return self._to_response(plan)

    def update_plan(
        self,
        db: Session,
        *,
        plan_id: int,
        data: SubscriptionPlanUpdate,
    ) -> SubscriptionPlanResponse:
        plan = self.get_plan(db, plan_id)
        update_data = data.model_dump(exclude_unset=True)

        final_data: dict[str, Any] = {}

        for field in [
            "name",
            "description",
            "price_amount",
            "tokens_per_period",
            "max_generations_per_period",
            "priority",
            "is_public",
            "is_active",
            "sort_order",
        ]:
            if field in update_data:
                final_data[field] = update_data[field]

        if (
            "billing_interval" in update_data
            and update_data["billing_interval"] is not None
        ):
            final_data["billing_interval"] = (
                update_data["billing_interval"].value
            )

        if "currency" in update_data and update_data["currency"]:
            final_data["currency"] = update_data["currency"].upper()

        if "features" in update_data:
            final_data["features_json"] = self._serialize_json(
                update_data["features"]
            )

        if "metadata" in update_data:
            final_data["metadata_json"] = self._serialize_json(
                update_data["metadata"]
            )

        updated = subscription_plan_repository.update(
            db,
            db_obj=plan,
            data=final_data,
        )

        return self._to_response(updated)

    def set_active(
        self,
        db: Session,
        *,
        plan_id: int,
        is_active: bool,
    ) -> SubscriptionPlanResponse:
        plan = self.get_plan(db, plan_id)
        plan.is_active = is_active

        db.add(plan)
        db.commit()
        db.refresh(plan)

        if plan.stripe_product_id:
            try:
                stripe_client_service.update_product(
                    db,
                    product_id=plan.stripe_product_id,
                    name=plan.name,
                    description=plan.description,
                    active=is_active,
                    metadata=self._stripe_metadata(plan),
                )
            except Exception:
                # Local state remains authoritative if Stripe is unavailable.
                pass

        if plan.stripe_price_id:
            try:
                if is_active:
                    stripe_client_service.activate_price(
                        db,
                        price_id=plan.stripe_price_id,
                    )
                else:
                    stripe_client_service.deactivate_price(
                        db,
                        price_id=plan.stripe_price_id,
                    )
            except Exception:
                pass

        return self._to_response(plan)

    def delete_plan(
        self,
        db: Session,
        *,
        plan_id: int,
    ) -> None:
        plan = self.get_plan(db, plan_id)

        if plan.stripe_price_id:
            try:
                stripe_client_service.deactivate_price(
                    db,
                    price_id=plan.stripe_price_id,
                )
            except Exception:
                pass

        if plan.stripe_product_id:
            try:
                stripe_client_service.update_product(
                    db,
                    product_id=plan.stripe_product_id,
                    name=plan.name,
                    description=plan.description,
                    active=False,
                    metadata=self._stripe_metadata(plan),
                )
            except Exception:
                pass

        subscription_plan_repository.delete(
            db,
            db_obj=plan,
        )

    def _amount_to_cents(self, value: Decimal) -> int:
        normalized = value.quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

        return int(normalized * 100)

    def _stripe_metadata(
        self,
        plan: SubscriptionPlan,
    ) -> dict[str, str]:
        return {
            "internal_plan_id": str(plan.id),
            "plan_key": plan.key,
            "billing_interval": plan.billing_interval,
            "tokens_per_period": str(plan.tokens_per_period),
        }

    def _price_matches_plan(
        self,
        stripe_price,
        plan: SubscriptionPlan,
    ) -> bool:
        expected_amount = self._amount_to_cents(plan.price_amount)
        expected_currency = plan.currency.lower()
        expected_interval = plan.billing_interval

        recurring = getattr(stripe_price, "recurring", None)

        if recurring is None and isinstance(stripe_price, dict):
            recurring = stripe_price.get("recurring")

        recurring_interval = None

        if recurring:
            if isinstance(recurring, dict):
                recurring_interval = recurring.get("interval")
            else:
                recurring_interval = getattr(
                    recurring,
                    "interval",
                    None,
                )

        unit_amount = getattr(stripe_price, "unit_amount", None)
        currency = getattr(stripe_price, "currency", None)
        active = getattr(stripe_price, "active", None)

        if isinstance(stripe_price, dict):
            unit_amount = stripe_price.get("unit_amount")
            currency = stripe_price.get("currency")
            active = stripe_price.get("active")

        return (
            unit_amount == expected_amount
            and currency == expected_currency
            and recurring_interval == expected_interval
            and active is True
        )

    def sync_plan_with_stripe(
        self,
        db: Session,
        *,
        plan_id: int,
    ) -> SubscriptionPlanSyncResponse:
        plan = self.get_plan(db, plan_id)
        metadata = self._stripe_metadata(plan)

        if not plan.stripe_product_id:
            stripe_product = stripe_client_service.create_product(
                db,
                name=plan.name,
                description=plan.description,
                active=plan.is_active,
                metadata=metadata,
            )

            plan.stripe_product_id = stripe_product.id
        else:
            stripe_product_service_result = (
                stripe_client_service.update_product(
                    db,
                    product_id=plan.stripe_product_id,
                    name=plan.name,
                    description=plan.description,
                    active=plan.is_active,
                    metadata=metadata,
                )
            )

            plan.stripe_product_id = (
                stripe_product_service_result.id
            )

        price_replaced = False
        existing_price_matches = False

        if plan.stripe_price_id:
            try:
                existing_price = (
                    stripe_client_service.retrieve_price(
                        db,
                        price_id=plan.stripe_price_id,
                    )
                )

                existing_price_matches = self._price_matches_plan(
                    existing_price,
                    plan,
                )
            except Exception:
                existing_price_matches = False

        if not existing_price_matches:
            old_price_id = plan.stripe_price_id

            new_price = stripe_client_service.create_recurring_price(
                db,
                product_id=plan.stripe_product_id,
                currency=plan.currency,
                unit_amount_cents=self._amount_to_cents(
                    plan.price_amount
                ),
                interval=plan.billing_interval,
                nickname=f"{plan.name} ({plan.billing_interval})",
                metadata=metadata,
            )

            plan.stripe_price_id = new_price.id
            price_replaced = bool(old_price_id)

            if old_price_id:
                try:
                    stripe_client_service.deactivate_price(
                        db,
                        price_id=old_price_id,
                    )
                except Exception:
                    pass

        elif not plan.is_active and plan.stripe_price_id:
            stripe_client_service.deactivate_price(
                db,
                price_id=plan.stripe_price_id,
            )

        db.add(plan)
        db.commit()
        db.refresh(plan)

        integration_service.record_event(
            db,
            provider="stripe",
            event_type="subscription_plan.synced",
            entity_type="subscription_plan",
            entity_id=str(plan.id),
            payload={
                "plan_key": plan.key,
                "billing_interval": plan.billing_interval,
                "currency": plan.currency,
                "price_amount": str(plan.price_amount),
            },
            response={
                "stripe_product_id": plan.stripe_product_id,
                "stripe_price_id": plan.stripe_price_id,
                "price_replaced": price_replaced,
            },
        )

        return SubscriptionPlanSyncResponse(
            plan=self._to_response(plan),
            stripe_product_id=plan.stripe_product_id,
            stripe_price_id=plan.stripe_price_id,
            price_replaced=price_replaced,
            message="Subscription plan synchronized with Stripe.",
        )

    def seed_defaults(
        self,
        db: Session,
    ) -> SubscriptionPlanSeedResponse:
        defaults = [
            SubscriptionPlanCreate(
                key="starter_monthly",
                name="Starter Monthly",
                description="Starter monthly subscription.",
                billing_interval=BillingInterval.MONTH,
                currency="USD",
                price_amount=Decimal("9.99"),
                tokens_per_period=100,
                max_generations_per_period=None,
                priority=20,
                features=[
                    "100 tokens per month",
                    "Standard generation priority",
                    "Try-on history",
                ],
                metadata={
                    "plan_family": "starter",
                },
                is_public=True,
                is_active=True,
                sort_order=10,
            ),
            SubscriptionPlanCreate(
                key="starter_yearly",
                name="Starter Yearly",
                description="Starter annual subscription.",
                billing_interval=BillingInterval.YEAR,
                currency="USD",
                price_amount=Decimal("99.90"),
                tokens_per_period=1200,
                max_generations_per_period=None,
                priority=20,
                features=[
                    "1,200 tokens per year",
                    "Standard generation priority",
                    "Try-on history",
                ],
                metadata={
                    "plan_family": "starter",
                },
                is_public=True,
                is_active=True,
                sort_order=11,
            ),
            SubscriptionPlanCreate(
                key="pro_monthly",
                name="Pro Monthly",
                description="Professional monthly subscription.",
                billing_interval=BillingInterval.MONTH,
                currency="USD",
                price_amount=Decimal("24.99"),
                tokens_per_period=350,
                max_generations_per_period=None,
                priority=50,
                features=[
                    "350 tokens per month",
                    "High generation priority",
                    "High-quality mode",
                    "Footwear try-on",
                ],
                metadata={
                    "plan_family": "pro",
                },
                is_public=True,
                is_active=True,
                sort_order=20,
            ),
            SubscriptionPlanCreate(
                key="pro_yearly",
                name="Pro Yearly",
                description="Professional annual subscription.",
                billing_interval=BillingInterval.YEAR,
                currency="USD",
                price_amount=Decimal("249.90"),
                tokens_per_period=4200,
                max_generations_per_period=None,
                priority=50,
                features=[
                    "4,200 tokens per year",
                    "High generation priority",
                    "High-quality mode",
                    "Footwear try-on",
                ],
                metadata={
                    "plan_family": "pro",
                },
                is_public=True,
                is_active=True,
                sort_order=21,
            ),
        ]

        created = 0
        skipped = 0

        for item in defaults:
            existing = subscription_plan_repository.get_by_key(
                db,
                item.key,
            )

            if existing:
                skipped += 1
                continue

            self.create_plan(
                db,
                data=item,
            )
            created += 1

        return SubscriptionPlanSeedResponse(
            created=created,
            skipped=skipped,
            total=len(defaults),
        )


subscription_plan_service = SubscriptionPlanService()