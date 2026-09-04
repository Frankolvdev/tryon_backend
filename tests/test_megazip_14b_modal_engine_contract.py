from app.services.runtime_builder_service import RuntimeBuilderService


def test_modal_runtime_engine_config_uses_current_authoritative_residents():
    content = RuntimeBuilderService._modal_runtime_engine_toml("/models")
    assert "gpu_enabled = true" in content
    for resident in RuntimeBuilderService.DEFAULT_MODAL_RESIDENT_MODELS:
        assert f'"{resident}"' in content
    assert 'model_roots = ["/models"]' in content
    assert 'warmup_workflow = "/app/runtime/modal-snapshot-warmup.json"' in content


def test_modal_warmup_matches_current_authoritative_residents():
    content = RuntimeBuilderService._modal_snapshot_warmup_workflow()
    for resident in RuntimeBuilderService.DEFAULT_MODAL_RESIDENT_MODELS:
        assert resident.split("/", 1)[-1] in content
    assert "TryonSnapshotWarmupSink" in content
    assert "flux2-vae.safetensors" not in content
    assert "sam3.pt" not in content


def test_modal_app_keeps_pipeline_and_runtime_engine_hooks():
    content = RuntimeBuilderService._modal_app("test-models", "/models", "test-runtime")
    assert "def run_pipeline(self, payload):" in content
    assert "from generation_runtime import GenerationRuntime" in content
    assert "ModalSnapshotAdapter" in content
    assert "snapshot_adapter.prepare_snapshot()" in content
    assert "adapter.after_restore()" in content
    assert "RUNTIME_ENGINE_ENABLED = True" in content
