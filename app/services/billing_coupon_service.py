import json
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.common.billing_enums import CouponDiscountType
from app.common.exceptions import ConflictException, NotFoundException
from app.common.time import utc_now
from app.models.billing_coupon import BillingCoupon
from app.repositories.billing_coupon_repository import (
    billing_coupon_repository,
)
from app.schemas.billing_coupon import (
    BillingCouponCreate,
    BillingCouponListResponse,
    BillingCouponResponse,
    BillingCouponSyncResponse,
    BillingCouponUpdate,
    BillingCouponValidationResponse,
)
from app.services.integration_service import integration_service
from app.services.stripe_client_service import stripe_client_service


class BillingCouponService:
    def _serialize(self, value: Any) -> str:
        return json.dumps(
            value or {},
            ensure_ascii=False,
            default=str,
        )

    def _parse(self, value: str | None) -> dict[str, Any]:
        if not value:
            return {}

        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def _response(
        self,
        coupon: BillingCoupon,
    ) -> BillingCouponResponse:
        return BillingCouponResponse(
            id=coupon.id,
            code=coupon.code,
            name=coupon.name,
            description=coupon.description,
            discount_type=coupon.discount_type,
            duration=coupon.duration,
            duration_in_months=coupon.duration_in_months,
            percentage_off=coupon.percentage_off,
            amount_off=coupon.amount_off,
            currency=coupon.currency,
            stripe_coupon_id=coupon.stripe_coupon_id,
            stripe_promotion_code_id=(
                coupon.stripe_promotion_code_id
            ),
            stripe_configured=bool(
                coupon.stripe_coupon_id
                and coupon.stripe_promotion_code_id
            ),
            max_redemptions=coupon.max_redemptions,
            redemption_count=coupon.redemption_count,
            first_time_transaction_only=(
                coupon.first_time_transaction_only
            ),
            minimum_amount=coupon.minimum_amount,
            valid_from=coupon.valid_from,
            valid_until=coupon.valid_until,
            is_active=coupon.is_active,
            metadata=self._parse(coupon.metadata_json),
            created_at=coupon.created_at,
            updated_at=coupon.updated_at,
        )

    def get_coupon(
        self,
        db: Session,
        *,
        coupon_id: int,
    ) -> BillingCoupon:
        coupon = billing_coupon_repository.get_by_id(
            db,
            coupon_id,
        )

        if not coupon:
            raise NotFoundException(
                "Billing coupon not found."
            )

        return coupon

    def list_coupons(
        self,
        db: Session,
        *,
        search: str | None = None,
        is_active: bool | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> BillingCouponListResponse:
        coupons = billing_coupon_repository.list_filtered(
            db,
            search=search,
            is_active=is_active,
            skip=skip,
            limit=limit,
        )

        total = billing_coupon_repository.count_filtered(
            db,
            search=search,
            is_active=is_active,
        )

        return BillingCouponListResponse(
            items=[self._response(item) for item in coupons],
            total=total,
            skip=skip,
            limit=limit,
        )

    def create_coupon(
        self,
        db: Session,
        *,
        data: BillingCouponCreate,
    ) -> BillingCouponResponse:
        existing = billing_coupon_repository.get_by_code(
            db,
            data.code,
        )

        if existing:
            raise ConflictException(
                "Coupon code already exists."
            )

        coupon = billing_coupon_repository.create(
            db,
            data={
                "code": data.code.upper(),
                "name": data.name,
                "description": data.description,
                "discount_type": data.discount_type.value,
                "duration": data.duration.value,
                "duration_in_months": data.duration_in_months,
                "percentage_off": data.percentage_off,
                "amount_off": data.amount_off,
                "currency": (
                    data.currency.upper()
                    if data.currency
                    else None
                ),
                "max_redemptions": data.max_redemptions,
                "redemption_count": 0,
                "first_time_transaction_only": (
                    data.first_time_transaction_only
                ),
                "minimum_amount": data.minimum_amount,
                "valid_from": data.valid_from,
                "valid_until": data.valid_until,
                "is_active": data.is_active,
                "metadata_json": self._serialize(data.metadata),
            },
        )

        return self._response(coupon)

    def update_coupon(
        self,
        db: Session,
        *,
        coupon_id: int,
        data: BillingCouponUpdate,
    ) -> BillingCouponResponse:
        coupon = self.get_coupon(
            db,
            coupon_id=coupon_id,
        )

        values = data.model_dump(exclude_unset=True)
        final_data: dict[str, Any] = {}

        for field in [
            "name",
            "description",
            "max_redemptions",
            "first_time_transaction_only",
            "minimum_amount",
            "valid_from",
            "valid_until",
            "is_active",
        ]:
            if field in values:
                final_data[field] = values[field]

        if "metadata" in values:
            final_data["metadata_json"] = self._serialize(
                values["metadata"]
            )

        updated = billing_coupon_repository.update(
            db,
            db_obj=coupon,
            data=final_data,
        )

        if (
            updated.stripe_promotion_code_id
            and "is_active" in final_data
        ):
            stripe_client_service.update_promotion_code_active(
                db,
                promotion_code_id=(
                    updated.stripe_promotion_code_id
                ),
                active=updated.is_active,
                metadata={
                    "internal_coupon_id": str(updated.id),
                    "coupon_code": updated.code,
                },
            )

        return self._response(updated)

    def sync_with_stripe(
        self,
        db: Session,
        *,
        coupon_id: int,
    ) -> BillingCouponSyncResponse:
        coupon = self.get_coupon(
            db,
            coupon_id=coupon_id,
        )

        metadata = {
            "internal_coupon_id": str(coupon.id),
            "coupon_code": coupon.code,
        }

        if not coupon.stripe_coupon_id:
            stripe_coupon = stripe_client_service.create_coupon(
                db,
                name=coupon.name,
                discount_type=coupon.discount_type,
                percentage_off=coupon.percentage_off,
                amount_off=coupon.amount_off,
                currency=coupon.currency,
                duration=coupon.duration,
                duration_in_months=coupon.duration_in_months,
                max_redemptions=coupon.max_redemptions,
                redeem_by=coupon.valid_until,
                metadata=metadata,
                idempotency_key=(
                    f"billing-coupon-{coupon.id}"
                ),
            )

            coupon.stripe_coupon_id = stripe_coupon.id

        if not coupon.stripe_promotion_code_id:
            promotion_code = (
                stripe_client_service.create_promotion_code(
                    db,
                    coupon_id=coupon.stripe_coupon_id,
                    code=coupon.code,
                    active=coupon.is_active,
                    max_redemptions=coupon.max_redemptions,
                    expires_at=coupon.valid_until,
                    first_time_transaction_only=(
                        coupon.first_time_transaction_only
                    ),
                    minimum_amount=coupon.minimum_amount,
                    minimum_amount_currency=(
                        coupon.currency or "USD"
                    ),
                    metadata=metadata,
                    idempotency_key=(
                        f"billing-promotion-{coupon.id}"
                    ),
                )
            )

            coupon.stripe_promotion_code_id = (
                promotion_code.id
            )
        else:
            stripe_client_service.update_promotion_code_active(
                db,
                promotion_code_id=(
                    coupon.stripe_promotion_code_id
                ),
                active=coupon.is_active,
                metadata=metadata,
            )

        db.add(coupon)
        db.commit()
        db.refresh(coupon)

        integration_service.record_event(
            db,
            provider="stripe",
            event_type="billing_coupon.synced",
            entity_type="billing_coupon",
            entity_id=str(coupon.id),
            payload={
                "code": coupon.code,
                "discount_type": coupon.discount_type,
            },
            response={
                "stripe_coupon_id": coupon.stripe_coupon_id,
                "stripe_promotion_code_id": (
                    coupon.stripe_promotion_code_id
                ),
            },
        )

        return BillingCouponSyncResponse(
            coupon=self._response(coupon),
            stripe_coupon_id=coupon.stripe_coupon_id,
            stripe_promotion_code_id=(
                coupon.stripe_promotion_code_id
            ),
            message="Coupon synchronized with Stripe.",
        )

    def set_active(
        self,
        db: Session,
        *,
        coupon_id: int,
        active: bool,
    ) -> BillingCouponResponse:
        coupon = self.get_coupon(
            db,
            coupon_id=coupon_id,
        )

        coupon.is_active = active

        db.add(coupon)
        db.commit()
        db.refresh(coupon)

        if coupon.stripe_promotion_code_id:
            stripe_client_service.update_promotion_code_active(
                db,
                promotion_code_id=(
                    coupon.stripe_promotion_code_id
                ),
                active=active,
                metadata={
                    "internal_coupon_id": str(coupon.id),
                    "coupon_code": coupon.code,
                },
            )

        return self._response(coupon)

    def validate_code(
        self,
        db: Session,
        *,
        code: str,
        purchase_amount: Decimal | None = None,
    ) -> BillingCouponValidationResponse:
        coupon = billing_coupon_repository.get_by_code(
            db,
            code.upper(),
        )

        if not coupon:
            return BillingCouponValidationResponse(
                valid=False,
                coupon=None,
                message="Coupon code was not found.",
            )

        now = utc_now()

        if not coupon.is_active:
            return BillingCouponValidationResponse(
                valid=False,
                coupon=self._response(coupon),
                message="Coupon is disabled.",
            )

        if coupon.valid_from and coupon.valid_from > now:
            return BillingCouponValidationResponse(
                valid=False,
                coupon=self._response(coupon),
                message="Coupon is not active yet.",
            )

        if coupon.valid_until and coupon.valid_until <= now:
            return BillingCouponValidationResponse(
                valid=False,
                coupon=self._response(coupon),
                message="Coupon has expired.",
            )

        if (
            coupon.max_redemptions is not None
            and coupon.redemption_count
            >= coupon.max_redemptions
        ):
            return BillingCouponValidationResponse(
                valid=False,
                coupon=self._response(coupon),
                message="Coupon redemption limit was reached.",
            )

        if (
            coupon.minimum_amount is not None
            and purchase_amount is not None
            and purchase_amount < coupon.minimum_amount
        ):
            return BillingCouponValidationResponse(
                valid=False,
                coupon=self._response(coupon),
                message=(
                    "Purchase amount does not meet the coupon minimum."
                ),
            )

        if not coupon.stripe_promotion_code_id:
            return BillingCouponValidationResponse(
                valid=False,
                coupon=self._response(coupon),
                message="Coupon is not synchronized with Stripe.",
            )

        return BillingCouponValidationResponse(
            valid=True,
            coupon=self._response(coupon),
            message="Coupon is valid.",
        )


billing_coupon_service = BillingCouponService()