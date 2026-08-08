from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_modal_remote_capacity_is_not_redis_worker_count():
    source = text("app/services/generation_job_orchestrator_service.py")
    assert "GENERATION_MODAL_QUEUE_DISPATCHERS" in source
    assert "self._modal_capacity" in source
    assert "self._modal_queue_dispatchers" in source
    assert '("modal", max(1, int(self._runtime_settings.modal_max_containers)' not in source
    assert "target=self._modal_dispatch_loop" in source


def test_modal_result_wait_is_async_and_has_no_normal_poll_interval():
    adapter = text("app/services/modal_pipeline_adapter_service.py")
    block = adapter.split("async def await_result_async", 1)[1].split("def cancel_call", 1)[0]
    assert "await call.get.aio" in block
    assert "poll_interval" not in block
    assert "submit_pipeline" not in block


def test_modal_running_recovery_supervises_same_call_instead_of_requeueing():
    source = text("app/services/generation_job_orchestrator_service.py")
    recovery = source.split("def recover_pending", 1)[1].split("def _fail_orphaned_job", 1)[0]
    assert "item.provider_job_id" in recovery
    assert "_schedule_modal_supervision(item.id)" in recovery
    modal_branch = recovery.split("if item.engine == GenerationExecutionEngine.MODAL", 1)[1].split("continue", 1)[0]
    assert "generation_job_queue_service.enqueue" not in modal_branch
    assert 'item.status = "queued"' not in recovery


def test_modal_capacity_reserves_before_redis_dequeue():
    source = text("app/services/generation_job_orchestrator_service.py")
    block = source.split("def _modal_dispatch_loop", 1)[1].split("def _schedule_modal_supervision", 1)[0]
    assert block.index("_acquire_modal_reservation") < block.index("generation_job_queue_service.dequeue")
    assert "current.status != \"queued\"" in block


def test_modal_finalization_reuses_existing_billing_and_output_services():
    runtime = text("app/services/generation_module_runtime_service.py")
    block = runtime.split("def finalize_modal_supervised", 1)[1].split("def _run_modal_module", 1)[0]
    assert "_persist_final_outputs" in block
    assert "_materialize_modal_files" in block
    assert "_finalize_dynamic_billing" in block
    assert "billing_breakdown" not in block  # no second billing model invented here
    assert "result_locked" not in block      # existing dynamic billing owns lock/debt rules


def test_async_supervision_keeps_live_ui_state_without_provider_polling():
    runtime = text("app/services/generation_module_runtime_service.py")
    wait_block = runtime.split("async def await_modal_result_async", 1)[1].split("def finalize_modal_supervised", 1)[0]
    heartbeat_block = runtime.split("def _modal_supervision_heartbeat", 1)[1].split("async def await_modal_result_async", 1)[0]
    assert "asyncio.wait" in wait_block
    assert "_modal_supervision_heartbeat" in wait_block
    assert "provider_status = \"RUNNING\"" in heartbeat_block
    assert "generation_module_execution_store_service.save" not in heartbeat_block


def test_restart_stampede_protection_and_bounded_local_finalizers_exist():
    source = text("app/services/generation_job_orchestrator_service.py")
    assert "self.recover_pending()" in source
    assert source.index("self.recover_pending()") < source.index("target=self._modal_dispatch_loop")
    assert "GENERATION_MODAL_FINALIZER_WORKERS" in source
    assert "ThreadPoolExecutor" in source
    assert "await asyncio.to_thread" in source


def test_redis_pool_is_explicit_but_independent_of_modal_capacity():
    redis_source = text("app/core/redis_client.py")
    config = text("app/core/config.py")
    assert "REDIS_MAX_CONNECTIONS" in config
    assert "BlockingConnectionPool" in redis_source
    assert "max_connections=" in redis_source
    assert "REDIS_POOL_WAIT_SECONDS" in config
    assert "modal_max_containers" not in redis_source


def test_backend_settings_allow_thousand_plus_modal_containers():
    schema = text("app/schemas/ai_engine_settings.py")
    assert "modal_max_containers: int = Field(default=3, ge=1, le=100000)" in schema
    assert "modal_concurrency: int = Field(default=1, ge=1, le=16)" in schema
