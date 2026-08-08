from pathlib import Path


ORCHESTRATOR = Path("app/services/generation_job_orchestrator_service.py").read_text(encoding="utf-8")
RUNTIME = Path("app/services/generation_module_runtime_service.py").read_text(encoding="utf-8")
ADAPTER = Path("app/services/modal_pipeline_adapter_service.py").read_text(encoding="utf-8")


def _function_source(source: str, function_name: str) -> str:
    marker = f"    def {function_name}("
    async_marker = f"    async def {function_name}("
    start = source.find(marker)
    if start < 0:
        start = source.find(async_marker)
    assert start >= 0, f"{function_name} not found"
    remainder = source[start + 4 :]
    candidates = [
        pos for pos in (
            remainder.find("\n    def "),
            remainder.find("\n    async def "),
        )
        if pos >= 0
    ]
    if not candidates:
        return source[start:]
    return source[start : start + 4 + min(candidates)]


def test_startup_recovery_never_reissues_modal_spawn_or_cancel():
    recovery = _function_source(ORCHESTRATOR, "recover_pending")

    # Recovery may only attach to the already persisted provider job.
    assert "_register_modal_active(item.id)" in recovery
    assert "_schedule_modal_supervision(item.id)" in recovery
    assert "item.provider_job_id" in recovery

    # Absolutely no provider-side action may be repeated during recovery.
    assert "submit_pipeline(" not in recovery
    assert "spawn(" not in recovery
    assert "cancel_call(" not in recovery
    assert ".cancel(" not in recovery


def test_running_modal_recovery_is_not_requeued():
    recovery = _function_source(ORCHESTRATOR, "recover_pending")

    # Queued work can be restored to Redis, but running durable Modal calls cannot.
    modal_branch = recovery[recovery.find("if item.engine == GenerationExecutionEngine.MODAL") :]
    modal_branch = modal_branch[: modal_branch.find("# Preserve the established fail-closed behavior")]
    assert "generation_job_queue_service.enqueue" not in modal_branch
    assert "_schedule_modal_supervision(item.id)" in modal_branch


def test_cancel_requested_state_is_not_overwritten_by_modal_heartbeat():
    heartbeat = _function_source(RUNTIME, "_modal_supervision_heartbeat")

    # Heartbeat may only promote dispatch/in-queue presentation states.
    assert '"IN_QUEUE"' in heartbeat
    assert '"DISPATCHING"' in heartbeat
    assert '"DISPATCHING_TO_MODAL"' in heartbeat
    assert '"CANCEL_REQUESTED"' not in heartbeat

    # Therefore a recovered CANCEL_REQUESTED row stays visibly CANCEL_REQUESTED
    # until the same provider FunctionCall reaches a real terminal outcome.
    assert 'item.provider_status = "RUNNING"' in heartbeat


def test_backend_shutdown_does_not_cancel_provider_call():
    awaiter = _function_source(RUNTIME, "await_modal_result_async")
    assert "except asyncio.CancelledError" in awaiter
    assert "wait_task.cancel()" in awaiter
    assert "FunctionCall.cancel" in awaiter
    assert "recovery" in awaiter.lower()


def test_async_provider_wait_observes_same_call_id():
    waiter = _function_source(ADAPTER, "await_result_async")
    assert "call_id" in waiter
    assert "call.get.aio" in waiter
    assert "submit_pipeline(" not in waiter
    assert "spawn(" not in waiter
    assert "cancel_call(" not in waiter


def test_cancel_endpoint_remains_the_only_modal_cancel_driver():
    cancel_method = _function_source(RUNTIME, "cancel")
    recovery = _function_source(ORCHESTRATOR, "recover_pending")

    assert "modal_pipeline_adapter_service.cancel_call(" in cancel_method
    assert "modal_pipeline_adapter_service.cancel_call(" not in recovery


def test_recovery_failure_keeps_no_retry_contract():
    recovery = _function_source(ORCHESTRATOR, "recover_pending")
    assert "no retry was created" in recovery
    assert 'item.provider_status = "RECOVERY_FAILED"' in recovery
