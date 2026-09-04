from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_cashbox_keeps_profitability_surplus_separate_from_rounding_and_adds_cash_part_to_available():
    source = read("app/services/finance_cashbox_service.py")
    assert "profitability_surplus=sum(" in source
    assert "provider_profitability_credit=min(" in source
    assert "funding_state['provider_excess_credit_usd']))-provider_rounding_credit" in source
    assert "cash_profitability_surplus=max(" in source
    assert "total_available=released+realized_extra+cash_profitability_surplus" in source
    assert "released+rounding+profitability_surplus+expir" in source


def test_generation_finance_records_profitability_surplus_as_a_distinct_profit_component():
    source = read("app/services/generation_finance_service.py")
    assert "calculate_profitability_surplus(" in source
    assert '"profitability_surplus_for_company_usd"' in source
    assert "profit_after_benefits+profitability_surplus_float+rounding_surplus" in source


def test_api_contract_exposes_bag_profitability_surplus_without_repurposing_rounding():
    schema = read("app/schemas/finance_cashbox.py")
    assert "profitability_surplus_usd: float" in schema
    assert "profitability_surplus_total_usd: float" in schema
    assert "provider_profitability_credit_usd: float" in schema
    assert "rounding_surplus_usd: float" in schema
