from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_modal_deploy_propagates_runtime_profile_modal_environment_in_both_paths():
    source = (ROOT / "app/services/runtime_build_execution_service.py").read_text(encoding="utf-8")

    assert "def _runtime_modal_environment(db, build):" in source
    assert 'key.startswith("TRYON_MODAL_")' in source
    assert source.count(
        "**RuntimeBuildExecutionService._runtime_modal_environment(db, build)"
    ) == 2

    # Provider/engine-owned deployment controls must still be applied after the
    # runtime profile so a stale profile cannot override GPU/scaling settings.
    for key in (
        '"TRYON_MODAL_GPU": selected_gpu',
        '"TRYON_MODAL_REGION_MODE":',
        '"TRYON_MODAL_MIN_CONTAINERS":',
        '"TRYON_MODAL_EXECUTION_TIMEOUT":',
    ):
        assert key in source


def test_legacy_snapshot_has_no_automatic_sam3_warmup():
    source = (ROOT / "app/services/runtime_builder_service.py").read_text(encoding="utf-8")

    assert '"TRYON_MODAL_SNAPSHOT_MODEL_WARMUP", "false"' in source
    assert "SNAPSHOT_MODEL_WARMUP_TARGETS = ()" in source
    assert 'reason="no_legacy_warmup_targets"' in source
    assert "tryon-warmup-sam3" not in source
