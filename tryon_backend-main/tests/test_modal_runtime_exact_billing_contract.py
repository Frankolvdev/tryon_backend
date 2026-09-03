from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_generated_modal_runtime_attaches_exact_metrics_without_rewriting_pipeline():
    source = (ROOT / "app/services/runtime_builder_service.py").read_text(encoding="utf-8")
    assert 'result = runtime.execute(payload)' in source
    assert 'metrics["pipeline_duration_ms"] = duration_ms' in source
    assert 'metrics["duration_source"] = "runtime_exact"' in source
    assert '@modal.exit()' in source
    assert '_modal_trace("container_exit", role="pipeline_server")' in source


def test_generation_runtime_reports_exact_metrics_for_success_and_controlled_failure():
    runtime = (ROOT / "runpod_worker/generation_runtime/runtime.py").read_text(encoding="utf-8")
    metrics = (ROOT / "runpod_worker/generation_runtime/metrics.py").read_text(encoding="utf-8")
    assert 'metrics.snapshot(status="completed")' in runtime
    assert 'metrics.snapshot(status="failed", error=str(exc))' in runtime
    assert '"duration_source": "runtime_exact"' in metrics
    assert '"execution_time_ms": total_ms' in metrics
    assert '"termination_status": status' in metrics


def test_billing_prefers_runtime_exact_and_never_overwrites_it_with_backend_wall_clock():
    source = (ROOT / "app/services/generation_module_runtime_service.py").read_text(encoding="utf-8")
    assert 'duration_source = "runtime_exact"' in source
    assert '"provider_observed_cancelled"' in source
    assert 'duration_source = "backend_fallback"' in source
    assert 'elapsed_ms = max(elapsed_ms' not in source
    assert '"duration_source": duration_source' in source


def test_modal_failure_metrics_are_persisted_before_existing_failure_path_raises():
    source = (ROOT / "app/services/generation_module_runtime_service.py").read_text(encoding="utf-8")
    metrics_pos = source.index('runtime_metrics = copy.deepcopy(output.get("metrics") or {})')
    failure_pos = source.index('if output.get("status") != "completed":', metrics_pos)
    save_pos = source.index('generation_module_execution_store_service.save', metrics_pos)
    assert metrics_pos < save_pos < failure_pos
