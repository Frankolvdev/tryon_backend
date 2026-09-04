from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_financial_ledger_is_parallel_and_fifo():
    source = read("app/services/token_value_ledger_service.py")
    assert "order_by(TokenValueLot.created_at,TokenValueLot.id)" in source
    assert "legacy_untraced_balance" in source
    assert "effective_token_value_usd" in source


def test_generation_finance_preserves_infrastructure_and_v42_profit_components():
    source = read("app/services/generation_finance_service.py")
    assert 'cash_revenue=float(summary["recognized_revenue_usd"])' in source
    assert "company_profit=profit_after_benefits+profitability_surplus_float+rounding_surplus" in source
    assert "economic_total=infra+company_profit" in source
    assert "revenue=economic_total" in source
    assert "record.infrastructure_cost_usd=Decimal(str(round(infra,6)))" in source
    runtime = read("app/services/generation_module_runtime_service.py")
    assert "generation_finance_service.finalize" in runtime


def test_commercial_discount_scales_profit_by_product_tokens():
    source = read("app/services/financial_protection_service.py")
    assert "safe_profit_per_token_usd" in source
    assert "profit_budget=float(report.safe_profit_per_token_usd or 0) * token_count" in source
    assert "discount_amount=profit_budget*requested/100.0" in source
