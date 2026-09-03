from app.services.runtime_builder_service import RuntimeBuilderService


def test_modal_runtime_engine_is_hardcoded_on_for_build_generation():
    # The builder must install the Engine even when no profile/env config exists.
    assert RuntimeBuilderService.modal_runtime_engine_enabled(None) is True


def test_generated_modal_runtime_cannot_fall_back_to_env_disabled_engine():
    content = RuntimeBuilderService._modal_app("test-models", "/models", "test-runtime")

    assert "RUNTIME_ENGINE_ENABLED = True" in content
    assert 'RUNTIME_ENGINE_ENABLED = os.getenv(' not in content
    assert '"TRYON_MODAL_RUNTIME_ENGINE_ENABLED",\n    "false"' not in content
    assert "snapshot_adapter.prepare_snapshot()" in content
    assert "adapter.after_restore()" in content


def test_legacy_sam3_snapshot_warmup_remains_removed():
    source = RuntimeBuilderService._modal_app("test-models", "/models", "test-runtime")
    assert "tryon-warmup-sam3" not in source
