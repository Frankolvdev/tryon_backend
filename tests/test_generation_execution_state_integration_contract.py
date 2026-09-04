from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_active_executions_uses_shared_state_contract():
    source = (ROOT / "app/api/v1/endpoints/generation_modules.py").read_text(encoding="utf-8")
    assert "generation_execution_state_contract.is_active_for_client(item)" in source


def test_startup_recovery_does_not_requeue_cancel_requested_queued_work():
    source = (ROOT / "app/services/generation_job_orchestrator_service.py").read_text(encoding="utf-8")
    assert "generation_execution_state_contract.is_dispatchable(item)" in source


def test_modal_running_recovery_remains_durable_and_not_requeued():
    source = (ROOT / "app/services/generation_job_orchestrator_service.py").read_text(encoding="utf-8")
    assert "Running Modal work is NOT requeued" in source
    assert "item.engine == GenerationExecutionEngine.MODAL and item.provider_job_id" in source
    adapter = (ROOT / "app/services/modal_pipeline_adapter_service.py").read_text(encoding="utf-8")
    assert "FunctionCall.from_id" in adapter
