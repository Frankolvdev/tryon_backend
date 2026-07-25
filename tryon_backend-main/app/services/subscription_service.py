import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.time import utc_now
from app.common.billing_enums import (
    BillingProvider,
    SubscriptionStatus,
)
from app.common.exceptions import (
    ConflictException,
    NotFoundException,
)
from app.models.subscription_plan import SubscriptionPlan
from app.models.user import User
from app.models.user_subscription import UserSubscription
from app.repositories.billing_customer_repository import (
    billing_customer_repository,
)
from app.repositories.subscription_plan_repository import (
    subscription_plan_repository,
)
from app.repositories.user_subscription_repository import (
    user_subscription_repository,
)
from app.schemas.subscription import (
    AdminSubscriptionListResponse,
    SubscriptionActionResponse,
    SubscriptionChangePlanRequest,
    SubscriptionCheckoutRequest,
    SubscriptionCheckoutResponse,
    SubscriptionPortalResponse,
    SubscriptionSyncResponse,
    UserSubscriptionResponse,
)
from app.services.billing_customer_service import (
    billing_customer_service,
)
from app.services.integration_service import integration_service
from app.services.stripe_client_service import (
    stripe_client_service,
)
from app.services.subscription_plan_service import (
    subscription_plan_service,
)
from app.services.token_service import token_service


class SubscriptionService:
    def _serialize_json(self, value: Any) -> str:
        return json.dumps(
            value or {},
            ensure_ascii=False,
            default=str,
        )

    def _parse_json(self, value: str | None) -> dict[str, Any]:
        if not value:
            return {}

        try:
            parsed = json.loads(value)

            if isinstance(parsed, dict):
                return parsed

            return {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def _timestamp_to_datetime(
        self,
        value: int | float | None,
    ) -> datetime | None:
        if value is None:
            return None

        return datetime.fromtimestamp(
            value,
            tz=timezone.utc,
        ).replace(tzinfo=None)

    def _stripe_value(
        self,
        obj: Any,
        key: str,
        default: Any = None,
    ) -> Any:
        if obj is None:
            return default

        if isinstance(obj, dict):
            return obj.get(key, default)

        return getattr(obj, key, default)

    def _stripe_dict(self, value: Any) -> dict[str, Any]:
        if value is None:
            return {}

        if isinstance(value, dict):
            return dict(value)

        to_dict_recursive = getattr(
            value,
            "to_dict_recursive",
            None,
        )

        if callable(to_dict_recursive):
            parsed = to_dict_recursive()

            if isinstance(parsed, dict):
                return parsed

        to_dict = getattr(
            value,
            "to_dict",
            None,
        )

        if callable(to_dict):
            parsed = to_dict()

            if isinstance(parsed, dict):
                return parsed

        return {}

    def _stripe_id(self, value: Any) -> str | None:
        if value is None:
            return None

        if isinstance(value, str):
            return value

        return self._stripe_value(value, "id")

    def _subscription_items(
        self,
        stripe_subscription: Any,
    ) -> list[Any]:
        items = self._stripe_value(
            stripe_subscription,
            "items",
            {},
        )

        items_data = self._stripe_value(
            items,
            "data",
            [],
        )

        return list(items_data or [])

    def _primary_subscription_item(
        self,
        stripe_subscription: Any,
    ) -> Any | None:
        items = self._subscription_items(stripe_subscription)

        if not items:
            return None

        return items[0]

    def _subscription_period_timestamp(
        self,
        stripe_subscription: Any,
        field_name: str,
    ) -> int | float | None:
        top_level_value = self._stripe_value(
            stripe_subscription,
            field_name,
        )

        if top_level_value is not None:
            return top_level_value

        primary_item = self._primary_subscription_item(
            stripe_subscription
        )

        return self._stripe_value(
            primary_item,
            field_name,
        )

    def _plan_features(
        self,
        plan: SubscriptionPlan,
    ) -> list[str]:
        if not plan.features_json:
            return []

        try:
            parsed = json.loads(plan.features_json)

            if not isinstance(parsed, list):
                return []

            return [str(item) for item in parsed]
        except (json.JSONDecodeError, TypeError):
            return []

    def _to_response(
        self,
        db: Session,
        subscription: UserSubscription,
    ) -> UserSubscriptionResponse:
        plan = subscription_plan_repository.get_by_id(
            db,
            subscription.subscription_plan_id,
        )

        if not plan:
            raise NotFoundException(
                "Subscription plan not found."
            )

        return UserSubscriptionResponse(
            id=subscription.id,
            user_id=subscription.user_id,
            subscription_plan_id=(
                subscription.subscription_plan_id
            ),
            billing_customer_id=(
                subscription.billing_customer_id
            ),
            provider=subscription.provider,
            provider_subscription_id=(
                subscription.provider_subscription_id
            ),
            status=subscription.status,
            plan_key=plan.key,
            plan_name=plan.name,
            billing_interval=plan.billing_interval,
            currency=plan.currency,
            price_amount=str(plan.price_amount),
            tokens_per_period=plan.tokens_per_period,
            priority=plan.priority,
            features=self._plan_features(plan),
            current_period_start=(
                subscription.current_period_start
            ),
            current_period_end=subscription.current_period_end,
            trial_start=subscription.trial_start,
            trial_end=subscription.trial_end,
            cancel_at=subscription.cancel_at,
            canceled_at=subscription.canceled_at,
            ended_at=subscription.ended_at,
            cancel_at_period_end=(
                subscription.cancel_at_period_end
            ),
            last_tokens_granted_at=(
                subscription.last_tokens_granted_at
            ),
            metadata=self._parse_json(
                subscription.metadata_json
            ),
            created_at=subscription.created_at,
            updated_at=subscription.updated_at,
        )

    def get_current_subscription(
        self,
        db: Session,
        *,
        user_id: int,
        require_existing: bool = True,
    ) -> UserSubscription | None:
        subscription = (
            user_subscription_repository.get_current_by_user_id(
                db,
                user_id=user_id,
            )
        )

        if not subscription and require_existing:
            raise NotFoundException(
                "Active subscription not found."
            )

        return subscription

    def get_current_response(
        self,
        db: Session,
        *,
        user_id: int,
    ) -> UserSubscriptionResponse:
        subscription = self.get_current_subscription(
            db,
            user_id=user_id,
            require_existing=True,
        )

        return self._to_response(db, subscription)

    def create_checkout(
        self,
        db: Session,
        *,
        user: User,
        data: SubscriptionCheckoutRequest,
    ) -> SubscriptionCheckoutResponse:
        current = self.get_current_subscription(
            db,
            user_id=user.id,
            require_existing=False,
        )

        if current:
            raise ConflictException(
                "User already has an active or pending subscription."
            )

        plan = subscription_plan_service.get_plan_by_key(
            db,
            data.plan_key,
            require_active=True,
        )

        if not plan.is_public:
            raise ConflictException(
                "Subscription plan is not publicly available."
            )

        if not plan.stripe_price_id:
            raise ConflictException(
                "Subscription plan is not synchronized with Stripe."
            )

        customer = (
            billing_customer_service.get_or_create_stripe_customer(
                db,
                user=user,
            )
        )

        checkout_session = (
            stripe_client_service.create_checkout_session(
                db,
                customer_email=None,
                customer_id=customer.provider_customer_id,
                mode="subscription",
                line_items=[
                    {
                        "price": plan.stripe_price_id,
                        "quantity": 1,
                    }
                ],
                success_url=str(data.success_url),
                cancel_url=str(data.cancel_url),
                allow_promotion_codes=(
                    data.allow_promotion_codes
                ),
                metadata={
                    "type": "subscription_checkout",
                    "internal_user_id": str(user.id),
                    "internal_plan_id": str(plan.id),
                    "plan_key": plan.key,
                },
                subscription_metadata={
                    "internal_user_id": str(user.id),
                    "internal_plan_id": str(plan.id),
                    "plan_key": plan.key,
                },
                client_reference_id=str(user.id),
                # A Checkout Session can expire, be completed, or be cancelled.
                # Reusing a permanent idempotency key would make Stripe return
                # that old Session on every later click instead of creating a
                # fresh checkout. Keep the key unique per checkout attempt while
                # still allowing Stripe SDK retries for this request to remain
                # idempotent.
                idempotency_key=(
                    f"subscription-checkout-"
                    f"{user.id}-{plan.id}-{uuid4().hex}"
                ),
            )
        )

        integration_service.record_event(
            db,
            provider=BillingProvider.STRIPE.value,
            event_type="subscription.checkout.created",
            entity_type="user",
            entity_id=str(user.id),
            payload={
                "plan_id": plan.id,
                "plan_key": plan.key,
                "stripe_price_id": plan.stripe_price_id,
            },
            response={
                "checkout_session_id": checkout_session.id,
                "checkout_url": checkout_session.url,
                "customer_id": customer.provider_customer_id,
            },
        )

        return SubscriptionCheckoutResponse(
            checkout_session_id=checkout_session.id,
            checkout_url=checkout_session.url,
            customer_id=customer.provider_customer_id,
            plan_key=plan.key,
        )

    def create_portal(
        self,
        db: Session,
        *,
        user: User,
        return_url: str,
    ) -> SubscriptionPortalResponse:
        customer = (
            billing_customer_repository.get_by_user_and_provider(
                db,
                user_id=user.id,
                provider=BillingProvider.STRIPE.value,
            )
        )

        if not customer:
            raise NotFoundException(
                "Billing customer not found."
            )

        portal = (
            stripe_client_service.create_customer_portal_session(
                db,
                customer_id=customer.provider_customer_id,
                return_url=return_url,
            )
        )

        return SubscriptionPortalResponse(
            portal_url=portal.url,
        )

    def cancel_at_period_end(
        self,
        db: Session,
        *,
        user_id: int,
    ) -> SubscriptionActionResponse:
        subscription = self.get_current_subscription(
            db,
            user_id=user_id,
        )

        if not subscription.provider_subscription_id:
            raise ConflictException(
                "Subscription is not linked to Stripe."
            )

        if subscription.cancel_at_period_end:
            return SubscriptionActionResponse(
                subscription=self._to_response(
                    db,
                    subscription,
                ),
                message=(
                    "Subscription is already scheduled for "
                    "cancellation."
                ),
            )

        stripe_subscription = (
            stripe_client_service
            .update_subscription_cancel_at_period_end(
                db,
                subscription_id=(
                    subscription.provider_subscription_id
                ),
                cancel_at_period_end=True,
            )
        )

        updated = self.sync_from_stripe_object(
            db,
            stripe_subscription=stripe_subscription,
        )

        return SubscriptionActionResponse(
            subscription=self._to_response(db, updated),
            message=(
                "Subscription will be canceled at the end "
                "of the current billing period."
            ),
        )

    def cancel_immediately(
        self,
        db: Session,
        *,
        user_id: int,
    ) -> SubscriptionActionResponse:
        subscription = self.get_current_subscription(
            db,
            user_id=user_id,
        )

        if not subscription.provider_subscription_id:
            raise ConflictException(
                "Subscription is not linked to Stripe."
            )

        stripe_subscription = (
            stripe_client_service.cancel_subscription_immediately(
                db,
                subscription_id=(
                    subscription.provider_subscription_id
                ),
                invoice_now=False,
                prorate=False,
            )
        )

        updated = self.sync_from_stripe_object(
            db,
            stripe_subscription=stripe_subscription,
        )

        return SubscriptionActionResponse(
            subscription=self._to_response(db, updated),
            message="Subscription canceled immediately.",
        )

    def reactivate(
        self,
        db: Session,
        *,
        user_id: int,
    ) -> SubscriptionActionResponse:
        subscription = self.get_current_subscription(
            db,
            user_id=user_id,
        )

        if not subscription.cancel_at_period_end:
            raise ConflictException(
                "Subscription is not scheduled for cancellation."
            )

        if not subscription.provider_subscription_id:
            raise ConflictException(
                "Subscription is not linked to Stripe."
            )

        stripe_subscription = (
            stripe_client_service
            .update_subscription_cancel_at_period_end(
                db,
                subscription_id=(
                    subscription.provider_subscription_id
                ),
                cancel_at_period_end=False,
            )
        )

        updated = self.sync_from_stripe_object(
            db,
            stripe_subscription=stripe_subscription,
        )

        return SubscriptionActionResponse(
            subscription=self._to_response(db, updated),
            message="Subscription reactivated successfully.",
        )

    def change_plan(
        self,
        db: Session,
        *,
        user_id: int,
        data: SubscriptionChangePlanRequest,
    ) -> SubscriptionActionResponse:
        subscription = self.get_current_subscription(
            db,
            user_id=user_id,
        )

        new_plan = subscription_plan_service.get_plan_by_key(
            db,
            data.new_plan_key,
            require_active=True,
        )

        if subscription.subscription_plan_id == new_plan.id:
            raise ConflictException(
                "User is already subscribed to this plan."
            )

        if not new_plan.stripe_price_id:
            raise ConflictException(
                "New plan is not synchronized with Stripe."
            )

        if not subscription.provider_subscription_id:
            raise ConflictException(
                "Subscription is not linked to Stripe."
            )

        stripe_subscription = (
            stripe_client_service.retrieve_subscription(
                db,
                subscription_id=(
                    subscription.provider_subscription_id
                ),
            )
        )

        primary_item = self._primary_subscription_item(
            stripe_subscription
        )

        subscription_item_id = self._stripe_value(
            primary_item,
            "id",
        )

        if not subscription_item_id:
            raise ConflictException(
                "Stripe subscription item ID is missing."
            )

        changed_subscription = (
            stripe_client_service.change_subscription_price(
                db,
                subscription_id=(
                    subscription.provider_subscription_id
                ),
                subscription_item_id=subscription_item_id,
                new_price_id=new_plan.stripe_price_id,
                proration_behavior=data.proration_behavior,
            )
        )

        updated = self.sync_from_stripe_object(
            db,
            stripe_subscription=changed_subscription,
            forced_plan=new_plan,
        )

        integration_service.record_event(
            db,
            provider=BillingProvider.STRIPE.value,
            event_type="subscription.plan_changed",
            entity_type="user_subscription",
            entity_id=str(updated.id),
            payload={
                "new_plan_id": new_plan.id,
                "new_plan_key": new_plan.key,
                "proration_behavior": data.proration_behavior,
            },
            response={
                "provider_subscription_id": (
                    updated.provider_subscription_id
                ),
                "status": updated.status,
            },
        )

        return SubscriptionActionResponse(
            subscription=self._to_response(db, updated),
            message="Subscription plan changed successfully.",
        )

    def synchronize_subscription(
        self,
        db: Session,
        *,
        user_id: int,
    ) -> SubscriptionSyncResponse:
        subscription = (
            user_subscription_repository.get_latest_by_user_id(
                db,
                user_id=user_id,
            )
        )

        if not subscription:
            raise NotFoundException(
                "Subscription not found."
            )

        if not subscription.provider_subscription_id:
            raise ConflictException(
                "Subscription is not linked to Stripe."
            )

        stripe_subscription = (
            stripe_client_service.retrieve_subscription(
                db,
                subscription_id=(
                    subscription.provider_subscription_id
                ),
            )
        )

        updated = self.sync_from_stripe_object(
            db,
            stripe_subscription=stripe_subscription,
        )

        return SubscriptionSyncResponse(
            subscription=self._to_response(db, updated),
            synchronized=True,
            message="Subscription synchronized with Stripe.",
        )

    def _resolve_plan_from_stripe_subscription(
        self,
        db: Session,
        *,
        stripe_subscription: Any,
        metadata: dict[str, Any],
        forced_plan: SubscriptionPlan | None,
    ) -> SubscriptionPlan:
        if forced_plan:
            return forced_plan

        plan_id_value = metadata.get("internal_plan_id")

        if plan_id_value:
            plan = subscription_plan_repository.get_by_id(
                db,
                int(plan_id_value),
            )

            if plan:
                return plan

        primary_item = self._primary_subscription_item(
            stripe_subscription
        )

        stripe_price = self._stripe_value(
            primary_item,
            "price",
        )

        stripe_price_id = self._stripe_id(stripe_price)

        if stripe_price_id:
            plan = (
                subscription_plan_repository
                .get_by_stripe_price_id(
                    db,
                    stripe_price_id,
                )
            )

            if plan:
                return plan

        raise NotFoundException(
            "Internal subscription plan could not be resolved."
        )

    def sync_from_stripe_object(
        self,
        db: Session,
        *,
        stripe_subscription: Any,
        forced_user_id: int | None = None,
        forced_plan: SubscriptionPlan | None = None,
    ) -> UserSubscription:
        stripe_subscription_id = self._stripe_value(
            stripe_subscription,
            "id",
        )

        if not stripe_subscription_id:
            raise ConflictException(
                "Stripe subscription ID is missing."
            )

        raw_metadata = self._stripe_value(
            stripe_subscription,
            "metadata",
            {},
        ) or {}

        metadata = self._stripe_dict(raw_metadata)

        existing = (
            user_subscription_repository
            .get_by_provider_subscription_id(
                db,
                provider_subscription_id=(
                    stripe_subscription_id
                ),
            )
        )

        user_id_value = (
            forced_user_id
            or metadata.get("internal_user_id")
        )

        if existing and not user_id_value:
            user_id_value = existing.user_id

        if not user_id_value:
            raise ConflictException(
                "Internal user ID is missing from subscription."
            )

        user_id = int(user_id_value)

        provider_customer_id = self._stripe_id(
            self._stripe_value(
                stripe_subscription,
                "customer",
            )
        )

        billing_customer = None

        if provider_customer_id:
            billing_customer = (
                billing_customer_repository
                .get_by_provider_customer_id(
                    db,
                    provider=BillingProvider.STRIPE.value,
                    provider_customer_id=provider_customer_id,
                )
            )

        plan = self._resolve_plan_from_stripe_subscription(
            db,
            stripe_subscription=stripe_subscription,
            metadata=metadata,
            forced_plan=forced_plan,
        )

        status = (
            self._stripe_value(
                stripe_subscription,
                "status",
                SubscriptionStatus.INCOMPLETE.value,
            )
            or SubscriptionStatus.INCOMPLETE.value
        )

        current_period_start = self._timestamp_to_datetime(
            self._subscription_period_timestamp(
                stripe_subscription,
                "current_period_start",
            )
        )

        current_period_end = self._timestamp_to_datetime(
            self._subscription_period_timestamp(
                stripe_subscription,
                "current_period_end",
            )
        )

        stored_metadata = (
            self._parse_json(existing.metadata_json)
            if existing
            else {}
        )

        merged_metadata = {
            **stored_metadata,
            **metadata,
            "stripe_price_id": plan.stripe_price_id,
        }

        values = {
            "user_id": user_id,
            "subscription_plan_id": plan.id,
            "billing_customer_id": (
                billing_customer.id
                if billing_customer
                else (
                    existing.billing_customer_id
                    if existing
                    else None
                )
            ),
            "provider": BillingProvider.STRIPE.value,
            "provider_subscription_id": (
                stripe_subscription_id
            ),
            "status": status,
            "current_period_start": current_period_start,
            "current_period_end": current_period_end,
            "trial_start": self._timestamp_to_datetime(
                self._stripe_value(
                    stripe_subscription,
                    "trial_start",
                )
            ),
            "trial_end": self._timestamp_to_datetime(
                self._stripe_value(
                    stripe_subscription,
                    "trial_end",
                )
            ),
            "cancel_at": self._timestamp_to_datetime(
                self._stripe_value(
                    stripe_subscription,
                    "cancel_at",
                )
            ),
            "canceled_at": self._timestamp_to_datetime(
                self._stripe_value(
                    stripe_subscription,
                    "canceled_at",
                )
            ),
            "ended_at": self._timestamp_to_datetime(
                self._stripe_value(
                    stripe_subscription,
                    "ended_at",
                )
            ),
            "cancel_at_period_end": bool(
                self._stripe_value(
                    stripe_subscription,
                    "cancel_at_period_end",
                    False,
                )
            ),
            "metadata_json": self._serialize_json(
                merged_metadata
            ),
        }

        if existing:
            updated = user_subscription_repository.update(
                db,
                db_obj=existing,
                data=values,
            )
        else:
            updated = user_subscription_repository.create(
                db,
                data=values,
            )

        return updated

    def retrieve_and_sync_provider_subscription(
        self,
        db: Session,
        *,
        provider_subscription_id: str,
    ) -> UserSubscription:
        stripe_subscription = stripe_client_service.retrieve_subscription(
            db,
            subscription_id=provider_subscription_id,
        )
        return self.sync_from_stripe_object(
            db,
            stripe_subscription=stripe_subscription,
        )

    def _get_subscription_for_update(
        self,
        db: Session,
        *,
        subscription_id: int,
    ) -> UserSubscription | None:
        statement = (
            select(UserSubscription)
            .where(UserSubscription.id == subscription_id)
            .with_for_update()
        )

        return db.execute(statement).scalar_one_or_none()

    def grant_period_tokens_if_needed(
        self,
        db: Session,
        *,
        subscription_id: int,
        reference_id: str,
    ) -> UserSubscription:
        subscription = self._get_subscription_for_update(
            db,
            subscription_id=subscription_id,
        )

        if not subscription:
            raise NotFoundException(
                "Subscription not found."
            )

        if subscription.status not in [
            SubscriptionStatus.ACTIVE.value,
            SubscriptionStatus.TRIALING.value,
            SubscriptionStatus.PAST_DUE.value,
        ]:
            db.rollback()

            raise ConflictException(
                "Subscription is not eligible for token allocation."
            )

        plan = subscription_plan_repository.get_by_id(
            db,
            subscription.subscription_plan_id,
        )

        if not plan:
            db.rollback()

            raise NotFoundException(
                "Subscription plan not found."
            )

        metadata = self._parse_json(
            subscription.metadata_json
        )

        granted_invoice_ids = metadata.get(
            "granted_token_invoice_ids",
            [],
        )

        if not isinstance(granted_invoice_ids, list):
            granted_invoice_ids = []

        if reference_id in granted_invoice_ids:
            db.commit()
            db.refresh(subscription)

            return subscription

        if plan.tokens_per_period <= 0:
            granted_invoice_ids.append(reference_id)

            metadata["granted_token_invoice_ids"] = (
                granted_invoice_ids[-50:]
            )
            metadata["last_token_grant_reference"] = (
                reference_id
            )
            metadata["last_token_grant_amount"] = 0

            subscription.last_tokens_granted_at = utc_now()
            subscription.metadata_json = self._serialize_json(
                metadata
            )

            db.add(subscription)
            db.commit()
            db.refresh(subscription)

            return subscription

        token_service.credit_tokens(
            db=db,
            user_id=subscription.user_id,
            amount=plan.tokens_per_period,
            source="subscription_period_grant",
            reference_id=reference_id,
            description=(
                f"Tokens incluidos en el plan {plan.name}"
            ),
        )

        granted_invoice_ids.append(reference_id)

        metadata["granted_token_invoice_ids"] = (
            granted_invoice_ids[-50:]
        )
        metadata["last_token_grant_reference"] = (
            reference_id
        )
        metadata["last_token_grant_amount"] = (
            plan.tokens_per_period
        )
        metadata["last_token_grant_plan_id"] = plan.id
        metadata["last_token_grant_plan_key"] = plan.key

        subscription.last_tokens_granted_at = utc_now()
        subscription.metadata_json = self._serialize_json(
            metadata
        )

        db.add(subscription)
        db.commit()
        db.refresh(subscription)

        integration_service.record_event(
            db,
            provider=BillingProvider.STRIPE.value,
            event_type="subscription.tokens_granted",
            entity_type="user_subscription",
            entity_id=str(subscription.id),
            payload={
                "user_id": subscription.user_id,
                "plan_id": plan.id,
                "plan_key": plan.key,
                "reference_id": reference_id,
            },
            response={
                "tokens_granted": plan.tokens_per_period,
                "last_tokens_granted_at": (
                    subscription.last_tokens_granted_at.isoformat()
                    if subscription.last_tokens_granted_at
                    else None
                ),
            },
        )

        return subscription

    def admin_list(
        self,
        db: Session,
        *,
        user_id: int | None = None,
        status: SubscriptionStatus | None = None,
        plan_id: int | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> AdminSubscriptionListResponse:
        status_value = status.value if status else None

        subscriptions = (
            user_subscription_repository.list_all_filtered(
                db,
                user_id=user_id,
                status=status_value,
                plan_id=plan_id,
                skip=skip,
                limit=limit,
            )
        )

        total = user_subscription_repository.count_filtered(
            db,
            user_id=user_id,
            status=status_value,
            plan_id=plan_id,
        )

        return AdminSubscriptionListResponse(
            items=[
                self._to_response(db, subscription)
                for subscription in subscriptions
            ],
            total=total,
            skip=skip,
            limit=limit,
        )


subscription_service = SubscriptionService()