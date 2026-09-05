from app.services.generation_result_mime import (
    is_generation_image,
    normalize_generation_content_type,
)


def test_generic_octet_stream_png_is_inferred_as_image():
    assert normalize_generation_content_type("application/octet-stream", "result.png") == "image/png"
    assert is_generation_image("application/octet-stream", "result.png") is True


def test_missing_mime_jpeg_is_inferred_as_image():
    assert normalize_generation_content_type(None, "face.jpg") == "image/jpeg"
    assert is_generation_image(None, "face.jpg") is True


def test_explicit_non_image_mime_is_not_overridden_by_extension():
    assert normalize_generation_content_type("application/pdf", "fake.png") == "application/pdf"
    assert is_generation_image("application/pdf", "fake.png") is False


def test_generic_unknown_extension_remains_non_image():
    assert normalize_generation_content_type("application/octet-stream", "payload.bin") == "application/octet-stream"
    assert is_generation_image("application/octet-stream", "payload.bin") is False


def test_explicit_image_mime_is_preserved():
    assert normalize_generation_content_type("image/webp", "anything.bin") == "image/webp"
    assert is_generation_image("image/webp", "anything.bin") is True
