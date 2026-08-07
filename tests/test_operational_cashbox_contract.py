from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def read(rel): return (ROOT/rel).read_text(encoding="utf-8")

def test_generation_token_math_never_reads_operational_reserve():
    pricing=read("app/services/pricing_service.py")
    body=pricing.split("def token_charge_for_infrastructure",1)[1].split("def get_commercial_settings",1)[0]
    assert "_operational_reserve" not in body
    assert "_commercial_sale_value" not in body
    assert "generation_infrastructure_capacity" in body

def test_commercial_sale_price_adds_operation_outside_generation_base():
    pricing=read("app/services/pricing_service.py")
    assert "return self._token_value(db) + self._operational_reserve(db)" in pricing
    assert "operational_reserve_per_token_usd: float" in read("app/schemas/pricing.py")

def test_operational_income_is_snapshot_driven_and_promotional_is_excluded():
    service=read("app/services/operational_cashbox_service.py")
    assert 'snapshot.get("operational_reserve_per_token")' in service
    assert 'lot.source == "promotional_credit"' in service
    assert "pricing_service._operational_reserve(db)" in service  # only current config display

def test_operational_funds_release_on_first_use_and_expiration():
    ledger=read("app/services/token_value_ledger_service.py")
    expiry=read("app/services/finance_cashbox_service.py")
    assert "release_on_activation" in ledger
    assert "release_on_expiration" in expiry

def test_operational_expenses_have_independent_ledger():
    model=read("app/models/operational_expense.py")
    assert '__tablename__ = "operational_expenses"' in model
    assert "FinanceWithdrawal" not in model
    assert "InfrastructureFunding" not in model
