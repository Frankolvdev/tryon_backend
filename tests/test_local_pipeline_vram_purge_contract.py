from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND_RUNTIME = ROOT / "app" / "services" / "generation_module_runtime_service.py"
REMOTE_RUNTIME = ROOT / "runpod_worker" / "generation_runtime" / "runtime.py"


def _backend_source() -> str:
    return BACKEND_RUNTIME.read_text(encoding="utf-8")


def _function_source(path: Path, name: str) -> str:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(source, node) or ""
    raise AssertionError(f"function {name!r} not found in {path}")


def test_backend_local_pipeline_purge_uses_windows_python_purge_node() -> None:
    source = _function_source(BACKEND_RUNTIME, "_utility_cleanup_workflow")
    assert '"class_type": "VRAM_Purge_Windows"' in source
    assert '"unload_models": True' in source
    assert '"empty_cache": True' in source
    assert '"synchronize": True' in source
    assert '"class_type": "LayerUtility: PurgeVRAM V2"' not in source
    assert "__TRYON_STAGE_BOUNDARY_FULL_PURGE__" not in source


def test_local_python_marker_reuses_the_same_blind_cleanup_workflow() -> None:
    source = _function_source(BACKEND_RUNTIME, "execute_python_step")
    assert "self._utility_cleanup_workflow()" in source
    assert '"LayerUtility: PurgeVRAM V2"' not in source
    assert "__TRYON_STAGE_BOUNDARY_FULL_PURGE__" not in source


def test_local_utility_dispatch_is_restricted_to_local_engines() -> None:
    source = _function_source(BACKEND_RUNTIME, "execute_utility_step")
    assert "GenerationExecutionEngine.LOCAL_DOCKER" in source
    assert "GenerationExecutionEngine.OWNER_LOCAL" in source
    assert "Modal/RunPod/Beam execute the full module inside the provider runtime" in source


def test_modal_provider_runtime_keeps_stage_boundary_guard_contract() -> None:
    # Regression shield: this hotfix is intentionally backend-local only.  The
    # provider runtime used by Modal keeps the already-proven sentinel + runtime
    # guard path untouched.
    source = REMOTE_RUNTIME.read_text(encoding="utf-8")
    assert '"class_type": "TryOn: StageBoundarySentinel"' in source
    assert '"class_type": "LayerUtility: PurgeVRAM V2"' in source
    assert "VRAM_PURGE_SOURCE_MARKER in source" in source
    assert "FULL VRAM purge started" in source
    assert "FULL VRAM purge completed" in source
