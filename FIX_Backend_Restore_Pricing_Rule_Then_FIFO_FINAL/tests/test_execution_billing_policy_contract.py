from pathlib import Path


def test_billing_policy_is_configurable_and_centralized():
    pricing = Path("app/services/pricing_service.py").read_text(encoding="utf-8")
    runtime = Path("app/services/generation_module_runtime_service.py").read_text(encoding="utf-8")
    endpoint = Path("app/api/v1/endpoints/admin/pricing.py").read_text(encoding="utf-8")
    assert "commercial_execution_billing_policy" in pricing
    assert "/execution-billing-policy" in endpoint
    assert "failed_workflow_or_user" in runtime
    assert "failed_platform_or_provider" in runtime
    assert "applied_profit_usd" in runtime
    assert "infrastructure_charge_applied" in runtime
    assert "pricing_service.token_charge_for_infrastructure(" in runtime
    assert "current_pricing_rule_then_fifo_allocation" in runtime


def test_default_policy_matches_agreed_rules():
    pricing = Path("app/services/pricing_service.py").read_text(encoding="utf-8")
    assert '"completed": {"charge_infrastructure": True, "apply_profit": True}' in pricing
    assert '"cancelled": {"charge_infrastructure": True, "apply_profit": False}' in pricing
    assert '"failed_workflow_or_user": {"charge_infrastructure": True, "apply_profit": False}' in pricing
    assert '"failed_platform_or_provider": {"charge_infrastructure": False, "apply_profit": False}' in pricing
