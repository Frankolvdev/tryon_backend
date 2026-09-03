from pathlib import Path


def test_modal_context_validator_accepts_hardcoded_engine_contract():
    source = Path("app/services/runtime_context_generator_service.py").read_text(encoding="utf-8")
    marker = "required_modal_fragments = ("
    start = source.index(marker)
    end = source.index("missing_fragments = [", start)
    contract = source[start:end]
    assert "'RUNTIME_ENGINE_ENABLED = True'" in contract
    assert "'TRYON_MODAL_RUNTIME_ENGINE_ENABLED'" not in contract


def test_modal_runtime_builder_remains_hardcoded_and_sam3_warmup_absent():
    source = Path("app/services/runtime_builder_service.py").read_text(encoding="utf-8")
    assert "RUNTIME_ENGINE_ENABLED = True" in source
    assert "def modal_runtime_engine_enabled" in source
    assert "SNAPSHOT_MODEL_WARMUP_TARGETS = ()" in source
    assert '"tryon-warmup-sam3"' not in source
