from decimal import Decimal

from app.schemas.billing_coupon import BillingCouponValidationResponse


def test_coupon_validation_response_preserves_backend_pricing_fields():
    response = BillingCouponValidationResponse(
        valid=True,
        message="Coupon is valid.",
        discount_amount=Decimal("14.85"),
        final_amount=Decimal("51.15"),
        requested_discount_percent=Decimal("25"),
        effective_discount_percent=Decimal("22.5"),
        protected_discount_percent=Decimal("100"),
        potential_loss_usd=Decimal("0"),
    )

    assert response.final_amount == Decimal("51.15")
    assert response.discount_amount == Decimal("14.85")
    assert response.requested_discount_percent == Decimal("25")
    assert response.effective_discount_percent == Decimal("22.5")
    assert response.protected_discount_percent == Decimal("100")
    assert response.potential_loss_usd == Decimal("0")
