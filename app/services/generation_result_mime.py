from __future__ import annotations

import mimetypes


_GENERIC_CONTENT_TYPES = {"", "application/octet-stream", "binary/octet-stream"}


def normalize_generation_content_type(content_type: str | None, filename: str | None) -> str:
    declared = str(content_type or "").strip().lower()
    guessed = (mimetypes.guess_type(str(filename or ""))[0] or "").strip().lower()

    if declared in _GENERIC_CONTENT_TYPES and guessed:
        return guessed
    return declared or guessed or "application/octet-stream"


def is_generation_image(content_type: str | None, filename: str | None) -> bool:
    return normalize_generation_content_type(content_type, filename).startswith("image/")
