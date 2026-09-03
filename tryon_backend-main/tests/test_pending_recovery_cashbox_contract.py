from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_pending_recovery_is_read_only_and_uses_existing_finance_breakdown():
    source = read("app/services/pending_recovery_service.py")
    assert "GenerationFinancialRecord" in source
    assert 'breakdown.get("settlement_pending")' in source
    assert 'breakdown.get("result_locked")' in source
    assert "token_charge_for_infrastructure" not in source
    assert "debit_tokens(" not in source
    assert "credit_tokens(" not in source


def test_pending_recovery_separates_exact_infrastructure_from_estimated_profit():
    source = read("app/services/pending_recovery_service.py")
    assert "infrastructure_pending" in source
    assert "profit_pending_estimate" in source
    assert "desired_profit_usd" in source
    assert "profit_after_customer_benefits_usd" in source


def test_cashbox_exposes_pending_recovery_without_changing_available_profit_formula():
    source = read("app/services/finance_cashbox_service.py")
    assert "pending_recovery_service.list_pending" in source
    # Existing green-cash formula remains intact.
    assert "available=max(D('0'),released+rounding+expir-D(str(withdrawals)))" in source
    assert "pending_recovery_infrastructure_usd" in source
