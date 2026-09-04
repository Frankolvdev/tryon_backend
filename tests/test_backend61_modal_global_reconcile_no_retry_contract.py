from pathlib import Path

ADAPTER = Path('app/services/modal_pipeline_adapter_service.py').read_text(encoding='utf-8')
ORCH = Path('app/services/generation_job_orchestrator_service.py').read_text(encoding='utf-8')
RUNTIME = Path('app/services/generation_module_runtime_service.py').read_text(encoding='utf-8')
BUILDER = Path('app/services/runtime_builder_service.py').read_text(encoding='utf-8')


def test_normal_modal_wait_has_no_call_graph_poll_loop():
    start = ADAPTER.index('    async def await_result_async(')
    end = ADAPTER.index('    async def inspect_terminal_failure_async(', start)
    body = ADAPTER[start:end]
    assert 'call.get.aio' in body
    assert 'get_call_graph' not in body
    assert 'spawn(' not in body
    assert 'submit_pipeline(' not in body


def test_global_reconciler_checks_supervised_calls_at_coarse_interval():
    assert 'GENERATION_MODAL_RECONCILE_SECONDS' in ORCH
    assert '_reconcile_modal_terminal_failures' in ORCH
    assert 'GENERATION_MODAL_RECONCILE_CONCURRENCY' in ORCH
    assert 'if not watched:' in ORCH
    # Terminal reconciliation is outside the lost-supervisor branch.
    assert 'run_coroutine_threadsafe' in ORCH


def test_terminal_child_failure_stops_same_call_without_spawn():
    assert 'inspect_terminal_failure_async' in ADAPTER
    assert 'INIT_FAILURE' in ADAPTER
    assert 'stop_failed_call_async' in ADAPTER
    stop = ADAPTER[ADAPTER.index('    async def stop_failed_call_async('):ADAPTER.index('    def cancel_call(', ADAPTER.index('    async def stop_failed_call_async('))]
    assert 'cancel' in stop
    assert 'spawn(' not in stop
    assert 'submit_pipeline(' not in stop


def test_runtime_marks_provider_failure_no_retry_created():
    assert 'reconcile_modal_terminal_failure_async' in RUNTIME
    assert 'No retry was created.' in RUNTIME


def test_generated_modal_function_still_has_zero_retries_and_pinned_engine():
    assert '"retries": 0' in BUILDER
    assert 'DEFAULT_RUNTIME_ENGINE_REF = "c18d48cebdf54a74dda0defeb570ae402a07b3f1"' in BUILDER
    assert 'runtime-engine-c18d48cebdf5-20260904' in BUILDER
