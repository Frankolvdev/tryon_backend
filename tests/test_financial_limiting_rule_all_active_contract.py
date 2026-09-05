from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE = (ROOT / "app/services/financial_protection_service.py").read_text(encoding="utf-8")
SCHEMA = (ROOT / "app/schemas/financial_protection.py").read_text(encoding="utf-8")


def test_active_rules_are_not_excluded_when_module_relation_is_missing_or_inactive():
    assert 'if not active:' in SERVICE
    assert 'if not active or module_id is None' not in SERVICE
    assert 'module is None or not module.is_active' not in SERVICE


def test_limiting_rule_is_selected_by_lowest_desired_profit():
    assert 'min(diagnostics, key=lambda item: item.desired_profit_usd)' in SERVICE


def test_diagnostics_allow_unassigned_active_rule():
    assert 'generation_module_id: int | None = None' in SCHEMA
    assert 'rule_title: str | None = None' in SCHEMA
