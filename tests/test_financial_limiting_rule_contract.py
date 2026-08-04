from pathlib import Path


def test_limiting_rule_is_selected_by_smallest_desired_profit():
    source = Path("app/services/financial_protection_service.py").read_text(encoding="utf-8")
    assert "min(diagnostics, key=lambda item: item.desired_profit_usd)" in source
    assert "min(enriched, key=lambda item: item[1])" not in source
    assert "They must never decide which rule is the highest-risk rule" in source


def test_report_identity_comes_from_desired_profit_limiting_rule():
    source = Path("app/services/financial_protection_service.py").read_text(encoding="utf-8")
    assert "limiting_pricing_rule_id=limiting_diagnostic.pricing_rule_id" in source
    assert "limiting_module_name=limiting_diagnostic.module_name" in source
