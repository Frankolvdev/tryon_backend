from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_execution_readiness_runs_before_token_charge_and_dispatch():
    text = (ROOT / "app/services/generation_module_runtime_service.py").read_text(encoding="utf-8")
    readiness = text.index("generation_configuration_readiness_service.ensure_ready")
    charge = text.index("generation_module_billing_service.charge", readiness)
    dispatch = text.index("generation_job_orchestrator_service.submit", readiness)
    assert readiness < charge < dispatch


def test_same_readiness_gate_covers_admin_test_and_user_execution():
    public_endpoint = (ROOT / "app/api/v1/endpoints/generation_modules.py").read_text(encoding="utf-8")
    admin_endpoint = (ROOT / "app/api/v1/endpoints/admin/generation_modules.py").read_text(encoding="utf-8")
    assert "generation_module_runtime_service.create(" in public_endpoint
    assert "generation_module_runtime_service.create(" in admin_endpoint


def test_readiness_validates_pricing_provider_gpu_and_token_value():
    text = (ROOT / "app/services/generation_configuration_readiness_service.py").read_text(encoding="utf-8")
    required = (
        "pricing_rule",
        "commercial_token_value_usd",
        "modal_scaledown_window_seconds",
        "runpod.idle_timeout_seconds",
        "beam.keep_warm_seconds",
        "gpu_cost_usd_per_second",
        "GENERATION_MODULE_MISSING_CONFIGURATION",
    )
    for marker in required:
        assert marker in text


def test_readiness_has_no_execution_side_effects():
    text = (ROOT / "app/services/generation_configuration_readiness_service.py").read_text(encoding="utf-8")
    forbidden = (
        "generation_module_billing_service.charge",
        "generation_job_orchestrator_service.submit",
        "FunctionCall",
        ".spawn(",
        "cancel(",
    )
    for marker in forbidden:
        assert marker not in text
