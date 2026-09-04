from pathlib import Path


def test_runtime_engine_clone_layer_has_explicit_cache_buster():
    source = Path("app/services/runtime_builder_service.py").read_text(encoding="utf-8")
    assert 'DEFAULT_RUNTIME_ENGINE_REF = "c18d48cebdf54a74dda0defeb570ae402a07b3f1"' in source
    assert 'DEFAULT_RUNTIME_ENGINE_CACHE_BUSTER = "runtime-engine-c18d48cebdf5-20260904"' in source
    assert 'ARG COMFY_RUNTIME_ENGINE_CACHE_BUSTER=' in source
    assert '[runtime] Runtime Engine cache buster: ${COMFY_RUNTIME_ENGINE_CACHE_BUSTER}' in source
    assert 'git clone --filter=blob:none ' in source
    assert 'rev-parse HEAD' in source
    assert 'Runtime Engine checkout SHA:' in source
    assert 'Runtime Engine guard sha256 source/installed:' in source


def test_engine_remains_hardcoded_on_and_sam3_warmup_remains_removed():
    source = Path("app/services/runtime_builder_service.py").read_text(encoding="utf-8")
    assert 'RUNTIME_ENGINE_ENABLED = True' in source
    assert 'SNAPSHOT_MODEL_WARMUP_TARGETS = ()' in source
