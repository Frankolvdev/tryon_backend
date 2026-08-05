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
from app.services.financial_protection_service import financial_protection_service


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


    def _applies_to(self, metadata: dict[str, Any]) -> list[str]:
        raw = metadata.get("applies_to", ["token_packages"])
        if isinstance(raw, str):
            raw = [raw]
        if not isinstance(raw, list):
            raw = []
        allowed = {"token_packages", "free_token_purchase"}
        values = [str(item) for item in raw if str(item) in allowed]
        return list(dict.fromkeys(values)) or ["token_packages"]

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
            applies_to=self._applies_to(self._parse(coupon.metadata_json)),
            eligible_item_ids=self._parse(coupon.metadata_json).get("eligible_item_ids", []),
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
        financial_protection_service.protected_price(
            db, nominal_price_usd=max(float(financial_protection_service.report(db).safe_profit_usd or 0), 0.01),
            requested_discount_percent=float(data.percentage_off or 0),
        )

        coupon = billing_coupon_repository.create(
            db,
            data={
                "code": data.code.upper(),
                "name": data.name,
                "description": data.description,
                "discount_type": CouponDiscountType.PERCENTAGE.value,
                "duration": data.duration.value,
                "duration_in_months": data.duration_in_months,
                "percentage_off": data.percentage_off,
                "amount_off": None,
                "currency": None,
                "max_redemptions": data.max_redemptions,
                "redemption_count": 0,
                "first_time_transaction_only": (
                    data.first_time_transaction_only
                ),
                "minimum_amount": data.minimum_amount,
                "valid_from": data.valid_from,
                "valid_until": data.valid_until,
                "is_active": data.is_active,
                "metadata_json": self._serialize({
                    **data.metadata,
                    "applies_to": data.applies_to,
                    "eligible_item_ids": data.eligible_item_ids,
                }),
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

        if any(key in values for key in ["metadata", "applies_to", "eligible_item_ids"]):
            merged_metadata = self._parse(coupon.metadata_json)
            if "metadata" in values and values["metadata"] is not None:
                merged_metadata.update(values["metadata"])
            if "applies_to" in values:
                merged_metadata["applies_to"] = values["applies_to"]
            if "eligible_item_ids" in values:
                merged_metadata["eligible_item_ids"] = values["eligible_item_ids"] or []
            final_data["metadata_json"] = self._serialize(merged_metadata)

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
        nominal_amount: Decimal | None = None,
        purchase_type: str | None = None,
        item_id: int | None = None,
        tokens_amount: int | None = None,
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

        metadata = self._parse(coupon.metadata_json)
        applies_to = self._applies_to(metadata)
        eligible_item_ids = metadata.get("eligible_item_ids", [])
        requested_scope = {"token_package": "token_packages", "free_token_purchase": "free_token_purchase"}.get(purchase_type)

        if requested_scope and requested_scope not in applies_to:
            return BillingCouponValidationResponse(valid=False, coupon=self._response(coupon), message="Coupon does not apply to this purchase type.")

        if item_id is not None and eligible_item_ids and item_id not in eligible_item_ids:
            return BillingCouponValidationResponse(valid=False, coupon=self._response(coupon), message="Coupon does not apply to the selected item.")


        if coupon.discount_type != CouponDiscountType.PERCENTAGE.value:
            return BillingCouponValidationResponse(
                valid=False, coupon=self._response(coupon),
                message="Only percentage coupons are supported.",
            )

        discount_amount = None
        final_amount = purchase_amount
        requested_percent = None
        effective_percent = None
        protected_percent = Decimal("100")
        if purchase_amount is not None and purchase_amount > 0:
            coupon_percent = Decimal(str(coupon.percentage_off or 0))
            existing_percent = Decimal("0")
            if purchase_type == "token_package" and item_id is not None:
                from app.repositories.token_package_repository import token_package_repository
                package = token_package_repository.get_by_id(db, item_id)
                if package is not None:
                    existing_percent = Decimal(str(package.requested_discount_percent or 0))
            combined_percent = existing_percent + coupon_percent
            requested_percent = combined_percent
            try:
                protected = financial_protection_service.protected_price(
                    db,
                    nominal_price_usd=float(nominal_amount or purchase_amount),
                    requested_discount_percent=float(coupon_percent),
                    existing_discount_percent=float(existing_percent),
                    tokens_amount=int(tokens_amount or 0),
                )
            except ConflictException as exc:
                report = financial_protection_service.report(db)
                safe_profit = Decimal(str(report.safe_profit_usd or 0))
                loss = max(Decimal("0"), combined_percent - Decimal("100")) * safe_profit / Decimal("100")
                return BillingCouponValidationResponse(
                    valid=False, coupon=self._response(coupon), message=str(exc),
                    requested_discount_percent=requested_percent, protected_discount_percent=protected_percent,
                    potential_loss_usd=loss,
                )
            effective_percent = Decimal(str(combined_percent))
            coupon_discount = Decimal(str(protected.discount_amount_usd)).quantize(Decimal("0.01"))
            final_amount = max(Decimal("0"), purchase_amount - coupon_discount).quantize(Decimal("0.01"))
            discount_amount = coupon_discount

        return BillingCouponValidationResponse(
            valid=True, coupon=self._response(coupon), message="Coupon is valid and will be calculated by the backend.",
            discount_amount=discount_amount, final_amount=final_amount,
            requested_discount_percent=requested_percent, effective_discount_percent=effective_percent,
            protected_discount_percent=protected_percent,
        )


billing_coupon_service = BillingCouponService()