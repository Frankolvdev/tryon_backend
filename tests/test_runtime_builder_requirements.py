from app.services.runtime_builder_service import RuntimeBuilderService


def test_extras_are_not_rendered_as_versions():
    assert RuntimeBuilderService.render_requirement(
        {"package": "qrcode", "version": "[pil]"}
    ) == "qrcode[pil]"


def test_empty_version_before_marker_is_removed():
    assert RuntimeBuilderService.render_requirement(
        {
            "package": "onnxruntime-gpu",
            "version": "; sys_platform != 'darwin' and platform_machine == 'x86_64'",
        }
    ) == 'onnxruntime-gpu; sys_platform != "darwin" and platform_machine == "x86_64"'


def test_normal_version_is_preserved():
    assert RuntimeBuilderService.render_requirement(
        {"package": "gguf", "version": "0.13.0"}
    ) == "gguf==0.13.0"
