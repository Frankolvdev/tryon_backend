from pathlib import Path

from app.services.runtime_builder_service import RuntimeBuilderService


def test_external_model_paths_use_universal_mount():
    yaml = RuntimeBuilderService._extra_model_paths_yaml('/models')
    assert 'base_path: /models' in yaml
    assert 'clip: text_encoders' in yaml
    assert 'diffusion_models: |' in yaml
    assert '    diffusion_models' in yaml
    assert '    unet' in yaml
    assert 'sam3: sam3' in yaml


def test_default_external_models_mount_is_provider_neutral():
    assert RuntimeBuilderService.DEFAULT_MODAL_VOLUME_PATH == '/models'


def test_generated_entrypoint_uses_direct_model_paths_and_workflow_volume():
    source = Path('app/services/runtime_builder_service.py').read_text(encoding='utf-8')
    context_source = Path('app/services/runtime_context_generator_service.py').read_text(encoding='utf-8')
    assert 'ln -s "$MODELS_ROOT/sam3"' not in source
    assert 'WORKFLOWS_ROOT="${{WORKFLOWS_ROOT:-/workflows}}"' in source
    assert '--user-directory "$COMFY_USER_ROOT"' in source
    assert 'ln -s "$MODELS_ROOT/sam3"' not in context_source
    assert '--user-directory "$COMFY_USER_ROOT"' in context_source
