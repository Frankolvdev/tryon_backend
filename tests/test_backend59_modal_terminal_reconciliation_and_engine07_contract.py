from pathlib import Path


def _function_source(source: str, function_name: str) -> str:
    for marker in (f"    def {function_name}(", f"    async def {function_name}("):
        start = source.find(marker)
        if start >= 0:
            break
    else:
        raise AssertionError(f"{function_name} not found")
    tail = source[start + 4 :]
    ends = [p for p in (tail.find("\n    def "), tail.find("\n    async def ")) if p >= 0]
    return source[start:] if not ends else source[start : start + 4 + min(ends)]


def test_runtime_engine_sha_pin_is_current():
    source = Path("app/services/runtime_builder_service.py").read_text(encoding="utf-8")
    assert 'DEFAULT_RUNTIME_ENGINE_REF = "c18d48cebdf54a74dda0defeb570ae402a07b3f1"' in source
    assert 'DEFAULT_RUNTIME_ENGINE_CACHE_BUSTER = "runtime-engine-c18d48cebdf5-20260904"' in source


def test_modal_async_wait_has_no_per_execution_graph_polling():
    source = Path("app/services/modal_pipeline_adapter_service.py").read_text(encoding="utf-8")
    waiter = _function_source(source, "await_result_async")
    assert "call.get.aio(timeout=remaining)" in waiter
    assert "get_call_graph" not in waiter
    assert "_GRAPH_WATCH_INTERVAL_SECONDS" not in source
    assert "asyncio.wait(" not in waiter


def test_modal_failure_path_never_reissues_generation():
    source = Path("app/services/modal_pipeline_adapter_service.py").read_text(encoding="utf-8")
    waiter = _function_source(source, "await_result_async")
    assert "submit_pipeline(" not in waiter
    assert ".spawn(" not in waiter
    assert "cancel_call(" not in waiter


def test_generated_modal_class_explicitly_disables_provider_retries():
    source = Path("app/services/runtime_builder_service.py").read_text(encoding="utf-8")
    start = source.index("MODAL_CLASS_OPTIONS = {{")
    end = source.index("@app.cls(**MODAL_CLASS_OPTIONS)", start)
    block = source[start:end]
    assert '"retries": 0' in block


def test_startup_recovery_keeps_same_provider_job_and_never_requeues_it():
    source = Path("app/services/generation_job_orchestrator_service.py").read_text(encoding="utf-8")
    recovery = _function_source(source, "recover_pending")
    modal_start = recovery.index("if item.engine == GenerationExecutionEngine.MODAL")
    modal_end = recovery.index("# Preserve the established fail-closed behavior", modal_start)
    modal_block = recovery[modal_start:modal_end]
    assert "item.provider_job_id" in modal_block
    assert "_schedule_modal_supervision(item.id)" in modal_block
    assert "generation_job_queue_service.enqueue" not in modal_block
    assert "spawn(" not in modal_block


def test_completed_status_still_requires_required_images_first():
    source = Path("app/services/generation_module_runtime_service.py").read_text(encoding="utf-8")
    start = source.index("def finalize_modal_supervised")
    end = source.index("def _run_modal_module", start)
    block = source[start:end]
    assert block.index("self._assert_required_image_outputs") < block.index('item.status = "completed"')
