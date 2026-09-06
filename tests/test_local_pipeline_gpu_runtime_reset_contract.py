from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "app/services/generation_module_runtime_service.py"
ADAPTER = ROOT / "app/services/comfyui_local_adapter_service.py"
REMOTE = ROOT / "runpod_worker/generation_runtime/runtime.py"


def test_local_pipeline_utility_uses_direct_runtime_reset_not_comfyui_workflow():
    source = RUNTIME.read_text(encoding="utf-8")
    start = source.index("    def execute_utility_step(")
    end = source.index("    def execute_python_step(", start)
    block = source[start:end]

    assert "full_gpu_runtime_reset(" in block
    assert "queue_prompt(" not in block
    assert "LayerUtility: PurgeVRAM V2" not in block
    assert "__TRYON_STAGE_BOUNDARY_FULL_PURGE__" not in block
    assert "EmptyImage" not in block
    assert "PreviewImage" not in block
    assert "DisplayAny" not in block


def test_legacy_python_marker_uses_same_direct_local_reset():
    source = RUNTIME.read_text(encoding="utf-8")
    start = source.index("    def execute_python_step(")
    block = source[start:]

    assert "full_gpu_runtime_reset(" in block
    marker_block = block[block.index("if self._VRAM_PURGE_SOURCE_MARKER in source:"):]
    assert "queue_prompt(" not in marker_block.split("        try:", 1)[0]


def test_local_adapter_calls_runtime_reset_endpoint_not_prompt():
    source = ADAPTER.read_text(encoding="utf-8")
    start = source.index("    def full_gpu_runtime_reset(")
    end = source.index("    def upload_input(", start)
    block = source[start:end]

    assert "/generation-runtime/gpu/reset" in block
    assert "/prompt" not in block
    assert "queue_prompt" not in block


def test_remote_provider_runtime_keeps_existing_stage_boundary_guard_contract():
    source = REMOTE.read_text(encoding="utf-8")
    assert '"class_type": "TryOn: StageBoundarySentinel"' in source
    assert '"class_type": "LayerUtility: PurgeVRAM V2"' in source
    assert "__TRYON_STAGE_BOUNDARY_FULL_PURGE__" not in source or "StageBoundarySentinel" in source
    assert "Pipeline Utility" in source
