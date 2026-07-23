from app.services.runtime_builder_service import RuntimeBuilderService


def test_requirement_extra_is_not_rendered_as_version():
    assert RuntimeBuilderService.render_requirement(
        {"package": "qrcode", "version": "[pil]"}
    ) == "qrcode[pil]"


def test_marker_is_not_rendered_as_version():
    marker = "; sys_platform != 'darwin' and platform_machine == 'x86_64'"
    assert RuntimeBuilderService.render_requirement(
        {"package": "onnxruntime-gpu", "version": marker}
    ) == f"onnxruntime-gpu{marker}"


def test_regular_version_keeps_exact_pin():
    assert RuntimeBuilderService.render_requirement(
        {"package": "gguf", "version": "0.13.0"}
    ) == "gguf==0.13.0"


def test_renderer_has_no_packaging_runtime_dependency():
    import app.services.runtime_builder_service as module

    assert "packaging" not in module.__dict__
