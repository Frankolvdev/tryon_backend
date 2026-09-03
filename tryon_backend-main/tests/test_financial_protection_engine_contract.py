from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_discount_engine_uses_desired_profit_only():
    source = text("app/services/financial_protection_service.py")
    assert "desired_profit_usd" in source
    assert "safe_profit_usd" in source
    assert "GPU costs are intentionally outside" in source
    assert "duration_safety_buffer_percent" not in source
    assert "gpu_cost_usd_per_second" not in source


def test_manual_protection_update_endpoint_is_removed():
    source = text("app/api/v1/endpoints/admin/pricing.py")
    assert '@router.get("/financial-protection"' in source
    assert '@router.patch("/financial-protection"' not in source


def test_coupons_are_percentage_only():
    schema = text("app/schemas/billing_coupon.py")
    service = text("app/services/billing_coupon_service.py")
    assert "Literal[CouponDiscountType.PERCENTAGE]" in schema
    create_section = schema.split("class BillingCouponCreate", 1)[1].split("class BillingCouponUpdate", 1)[0]
    assert "amount_off" not in create_section
    assert '"discount_type": CouponDiscountType.PERCENTAGE.value' in service


def test_plan_package_and_coupon_are_validated_by_profit_percentage():
    plans = text("app/services/subscription_plan_service.py")
    packages = text("app/services/token_service.py")
    coupons = text("app/services/billing_coupon_service.py")
    assert "requested_discount_percent" in plans
    assert "requested_discount_percent" in packages
    assert "existing_discount_percent" in coupons
    assert "combined_percent" in coupons
