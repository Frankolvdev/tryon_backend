from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_financial_engine_exposes_global_report_and_blocking():
    source = text("app/services/financial_protection_service.py")
    assert "protected_discount_percent" in source
    assert "calculated_maximum_safe_discount_percent" in source
    assert "available_headroom_percentage_points" in source
    assert "assert_report_safe" in source
    assert "Limiting module" in source


def test_dangerous_pricing_and_gpu_changes_use_same_gate():
    pricing = text("app/services/pricing_service.py")
    gpu = text("app/services/provider_pricing_service.py")
    assert "assert_rule_change" in pricing
    assert "assert_gpu_price_change" in gpu


def test_plans_and_packages_use_protected_commercial_price():
    plans = text("app/services/subscription_plan_service.py")
    packages = text("app/services/token_service.py")
    assert plans.count("protected_price(") >= 3
    assert packages.count("protected_price(") >= 3
    assert "requested_discount_percent" in plans
    assert "effective_discount_percent" in packages


def test_coupons_are_not_available_for_subscription_plans():
    schema = text("app/schemas/billing_coupon.py")
    subscription = text("app/services/subscription_service.py")
    assert 'Literal["token_packages", "free_token_purchase"]' in schema
    assert 'Literal["plan", "token_package"]' not in schema
    assert "allow_promotion_codes=False" in subscription


def test_token_checkout_applies_coupon_server_side_and_disables_stripe_generic_promos():
    checkout = text("app/services/token_purchase_service.py")
    schema = text("app/schemas/token_purchase.py")
    assert "coupon_code" in schema
    assert "billing_coupon_service.validate_code" in checkout
    assert "coupon_financial_snapshot" in checkout
    assert "nominal_amount=nominal_amount" in checkout
    assert "pre_coupon_amount" in checkout
    assert "allow_promotion_codes=False" in checkout


def test_migration_preserves_existing_package_prices_as_nominal_prices():
    migration = text("alembic/versions/7f4a9c2d1e80_add_financial_protection_catalog_fields.py")
    assert 'down_revision = "04a_dyn_pricing_resilience"' in migration
    assert "nominal_price_cents = price_cents" in migration


def test_generation_module_activation_and_provider_changes_are_guarded():
    source = text("app/services/generation_module_service.py")
    assert 'action="create generation module"' in source
    assert 'action="update generation module"' in source
    assert source.count("assert_report_safe") >= 2
