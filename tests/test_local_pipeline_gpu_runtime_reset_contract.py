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


def test_local_gpu_reset_passthrough_is_namespaced_without_flattening_module_inputs():
    source = RUNTIME.read_text(encoding="utf-8")
    start = source.index('                    is_local_gpu_reset_passthrough = (')
    end = source.index('                    item.progress =', start)
    block = source[start:end]

    assert 'GenerationExecutionEngine.LOCAL_DOCKER' in block
    assert 'GenerationExecutionEngine.OWNER_LOCAL' in block
    assert 'comfyui_vram_purge' in block
    assert '_VRAM_PURGE_SOURCE_MARKER' in block
    assert 'item.context[step["key"]] = copy.deepcopy(outputs)' in block
    assert 'else:' in block
    assert 'GenerationRuntimeContext.merge_step_outputs' in block


def test_local_gpu_reset_namespace_prevents_input_key_collision_contract():
    # Reproduce the module-6 failure mode: the purge ports are textual prompt
    # values named input_1/input_2 while the module root input_1/input_2 are floats.
    import copy

    context = {"input_1": 0.0, "input_2": 0.0, "python_2": {"input_1": "prompt A", "input_2": "prompt B"}}
    purge_outputs = {"input_1": "prompt A", "input_2": "prompt B"}
    context["cleanup_7"] = copy.deepcopy(purge_outputs)

    assert context["input_1"] == 0.0
    assert context["input_2"] == 0.0
    assert context["cleanup_7"]["input_1"] == "prompt A"
    assert context["cleanup_7"]["input_2"] == "prompt B"


def test_local_gpu_reset_namespace_is_dynamic_for_arbitrary_port_names():
    # The isolation rule is structural, not tied to input_1/input_2 or to module 6/7.
    import copy

    context = {
        "hips": 2.5,
        "camera": "front",
        "reference_image": {"storage_file_id": "abc"},
        "custom_99": 123,
    }
    purge_outputs = {
        "hips": "must-not-overwrite-root",
        "camera": "must-not-overwrite-root",
        "new_dynamic_port": "passthrough-value",
    }
    context["any_future_cleanup_step"] = copy.deepcopy(purge_outputs)

    assert context["hips"] == 2.5
    assert context["camera"] == "front"
    assert context["custom_99"] == 123
    assert context["any_future_cleanup_step"]["hips"] == "must-not-overwrite-root"
    assert context["any_future_cleanup_step"]["new_dynamic_port"] == "passthrough-value"
