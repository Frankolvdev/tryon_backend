from pathlib import Path


def test_execution_schema_persists_complete_pre_execution_estimate():
    source = Path("app/schemas/generation_module_runtime.py").read_text(encoding="utf-8")
    for field in (
        "estimated_duration_seconds",
        "estimated_duration_source",
        "estimated_billable_seconds",
        "estimated_infrastructure_cost_usd",
        "estimated_final_price_usd",
        "estimated_tokens_before_execution",
    ):
        assert field in source


def test_runtime_create_snapshots_estimate_before_charging_and_dispatch():
    source = Path("app/services/generation_module_runtime_service.py").read_text(encoding="utf-8")
    assert "applied_pricing = (" in source
    assert '"finalized": False' in source
    assert '"estimated_duration_seconds": estimated_duration_seconds' in source
    assert '"estimated_duration_source": estimated_duration_source' in source
    assert '"estimated_billable_seconds": estimated_billable_seconds' in source
    assert '"estimated_infrastructure_cost_usd": estimated_infrastructure_cost_usd' in source
    assert '"estimated_final_price_usd": estimated_final_price_usd' in source
    assert '"estimated_tokens_before_execution": estimated_tokens_before_execution' in source
    assert source.index("estimated_pricing_snapshot = {") < source.index("generation_module_billing_service.charge(")
    assert source.index("estimated_pricing_snapshot = {") < source.index("generation_job_orchestrator_service.submit(")


def test_final_billing_preserves_original_estimate_snapshot():
    source = Path("app/services/generation_module_runtime_service.py").read_text(encoding="utf-8")
    assert "estimated_snapshot = dict(item.billing_breakdown or {})" in source
    assert '"estimated_tokens_before_execution": initial_estimated_tokens' in source
    assert "**estimated_snapshot" in source
