from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_modal_recovery_reuses_existing_function_call():
    runtime = text("app/services/generation_module_runtime_service.py")
    adapter = text("app/services/modal_pipeline_adapter_service.py")
    orchestrator = text("app/services/generation_job_orchestrator_service.py")
    assert "existing_call_id=current.provider_job_id" in runtime
    assert "FunctionCall.from_id" in adapter
    assert "[backend-modal-resume]" in adapter
    assert 'item.status = "queued"' not in orchestrator.split("def recover_pending", 1)[1].split("def _fail_orphaned_job", 1)[0]


def test_failed_recovery_is_not_retried_without_provider_id():
    orchestrator = text("app/services/generation_job_orchestrator_service.py")
    recovery = orchestrator.split("def recover_pending", 1)[1].split("def _fail_orphaned_job", 1)[0]
    assert 'item.status = "failed"' in recovery
    assert "no retry was created" in recovery


def test_pricing_rule_has_new_commercial_inputs_and_legacy_compatibility():
    model = text("app/models/pricing_rule.py")
    schema = text("app/schemas/pricing.py")
    assert "desired_profit_usd" in model
    assert "initial_estimated_duration_seconds" in model
    assert "technical_margin_seconds" in model
    assert "average_execution_cost_usd" in schema
    assert "desired_profit_percent" in schema


def test_provider_gpu_prices_and_applied_simulation_endpoints_exist():
    endpoints = text("app/api/v1/endpoints/admin/pricing.py")
    assert '"/provider-gpu-prices"' in endpoints
    assert '"/applied-pricing-rules"' in endpoints
    assert "cost_usd_per_second" in text("app/models/provider_gpu_price.py")


def test_execution_exposes_real_time_and_immutable_billing_breakdown():
    schema = text("app/schemas/generation_module_runtime.py")
    runtime = text("app/services/generation_module_runtime_service.py")
    assert "real_provider_duration_ms" in schema
    assert "billing_breakdown" in schema
    assert "configured_scaledown_seconds" in runtime
    assert "technical_margin_seconds" in runtime
    assert "desired_profit_usd" in runtime
