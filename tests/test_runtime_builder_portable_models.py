from app.services.runtime_builder_service import RuntimeBuilderService


def test_external_model_paths_use_universal_mount():
    yaml = RuntimeBuilderService._extra_model_paths_yaml('/models')
    assert 'base_path: /models' in yaml
    assert 'clip: text_encoders' in yaml
    assert 'sam3: sam3' in yaml


def test_default_external_models_mount_is_provider_neutral():
    assert RuntimeBuilderService.DEFAULT_MODAL_VOLUME_PATH == '/models'
