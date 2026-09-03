from pathlib import Path


def _source() -> str:
    return Path("app/services/runtime_context_generator_service.py").read_text(encoding="utf-8")


def test_modal_dockerfile_gets_runtime_engine_cache_buster():
    source = _source()
    modal_start = source.index("def _modal_dockerfile")
    docker_start = source.index("def _dockerfile", modal_start)
    modal_source = source[modal_start:docker_start]

    assert '"ARG COMFY_RUNTIME_ENGINE_CACHE_BUSTER="' in modal_source
    assert "RuntimeBuilderService.DEFAULT_RUNTIME_ENGINE_CACHE_BUSTER" in modal_source
    assert '[runtime] Runtime Engine cache buster: ${COMFY_RUNTIME_ENGINE_CACHE_BUSTER}' in modal_source
    assert '"&& git clone --filter=blob:none "' in modal_source


def test_patch_is_scoped_to_modal_generator_contract():
    source = _source()
    modal_start = source.index("def _modal_dockerfile")
    docker_start = source.index("def _dockerfile", modal_start)
    modal_source = source[modal_start:docker_start]

    assert "COPY runtime-engine.toml /app/runtime/runtime-engine.toml" in modal_source
    assert "COPY modal-snapshot-warmup.json /app/runtime/modal-snapshot-warmup.json" in modal_source
    assert "DEFAULT_RUNTIME_ENGINE_INSTALL_PATH" in modal_source
