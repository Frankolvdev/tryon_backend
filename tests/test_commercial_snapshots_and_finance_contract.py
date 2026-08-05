from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")

def test_coupon_is_backend_priced_without_stripe_dependency():
    service = read("app/services/billing_coupon_service.py")
    assert "Coupon is not synchronized with Stripe" not in service
    assert "tokens_amount=int(tokens_amount or 0)" in service

def test_token_bags_freeze_commercial_terms():
    purchase = read("app/services/token_purchase_service.py")
    subscription = read("app/services/subscription_service.py")
    assert "commercial_terms_snapshot" in purchase
    assert "normal_profit_per_token_usd" in purchase
    assert "commercial_terms_snapshot" in subscription
    assert "next_period_commercial_terms_snapshot" in subscription

def test_finances_separate_provider_money_and_company_profit():
    ledger = read("app/services/token_value_ledger_service.py")
    finance = read("app/services/generation_finance_service.py")
    assert "benefit_given_usd" in ledger
    assert "company_profit_usd" in ledger
    assert "money_reserved_for_ai_provider_usd" in finance

def test_archived_plan_stops_next_renewal():
    plans = read("app/services/subscription_plan_service.py")
    assert '"renewal_disabled": True' in plans
    assert '"tokens_next_period_disabled": True' in plans
    assert "cancel_at_period_end=True" in plans
