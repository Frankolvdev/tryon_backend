
from pathlib import Path


def test_engine07_cache_buster_is_current():
    source = Path("app/services/runtime_builder_service.py").read_text(encoding="utf-8")
    assert 'DEFAULT_RUNTIME_ENGINE_CACHE_BUSTER = "runtime-engine-07-python310-tomli-20260903"' in source


def test_modal_async_wait_watches_terminal_graph_states():
    source = Path("app/services/modal_pipeline_adapter_service.py").read_text(encoding="utf-8")
    assert "_FAILED_GRAPH_STATES" in source
    assert "_call_graph_states_async" in source
    assert "failure state(s)" in source
    assert "reported terminal SUCCESS" in source


def test_completed_status_still_requires_required_images_first():
    source = Path("app/services/generation_module_runtime_service.py").read_text(encoding="utf-8")
    start = source.index("def finalize_modal_supervised")
    end = source.index("def _run_modal_module", start)
    block = source[start:end]
    assert block.index("self._assert_required_image_outputs") < block.index('item.status = "completed"')
