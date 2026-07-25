from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PromptPreprocessorResult:
    prompt: dict[str, Any]
    normalized_values: int


class ComfyUIPromptPreprocessorService:
    """Normaliza rutas del prompt sin modificar rgthree ni otros Custom Nodes."""

    _PATH_KEYS = {
        "path",
        "file_path",
        "filepath",
        "filename",
        "file_name",
        "image",
        "image_path",
        "mask",
        "mask_path",
        "lora",
        "loras",
        "lora_name",
        "lora_path",
        "ckpt_name",
        "checkpoint",
        "checkpoint_name",
        "checkpoint_path",
        "vae",
        "vae_name",
        "vae_path",
        "control_net_name",
        "controlnet",
        "controlnet_name",
        "controlnet_path",
        "clip_name",
        "clip_path",
        "clip_vision",
        "clip_vision_name",
        "clip_vision_path",
        "embedding",
        "embedding_name",
        "embedding_path",
        "style_model",
        "style_model_name",
        "style_model_path",
        "upscale_model",
        "upscale_model_name",
        "upscale_model_path",
        "model",
        "model_name",
        "model_path",
        "unet_name",
        "diffusion_model",
        "diffusion_model_name",
        "audio_encoder_name",
        "photomaker_model_name",
        "output_path",
        "output_directory",
        "subfolder",
        "directory",
        "folder",
    }

    _PATH_KEY_PATTERN = re.compile(
        r"(?:^|_)(?:path|file|filename|folder|directory|"
        r"lora|loras|checkpoint|ckpt|vae|controlnet|control_net|"
        r"clip|embedding|model|unet|image|mask)(?:$|_)",
        re.IGNORECASE,
    )
    _WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:[\\/]")
    _UNC_PATH = re.compile(r"^\\\\[^\\]+\\[^\\]+")
    _MODEL_EXTENSION = re.compile(
        r"\.(?:safetensors|ckpt|pt|pth|bin|onnx|engine|gguf|"
        r"png|jpe?g|webp|gif|bmp|tiff?|exr|npy|npz|json|yaml|yml)$",
        re.IGNORECASE,
    )

    @classmethod
    def preprocess(cls, prompt: dict[str, Any]) -> dict[str, Any]:
        return cls.preprocess_with_result(prompt).prompt

    @classmethod
    def preprocess_with_result(
        cls,
        prompt: dict[str, Any],
    ) -> PromptPreprocessorResult:
        if not isinstance(prompt, dict):
            raise TypeError("ComfyUI prompt must be a dictionary.")

        cloned = copy.deepcopy(prompt)
        normalized, count = cls._walk(cloned, parent_key=None)
        return PromptPreprocessorResult(
            prompt=normalized,
            normalized_values=count,
        )

    @staticmethod
    def _normalize_path(value: str) -> str:
        normalized = value.replace("\\", "/")
        while "//" in normalized and not normalized.startswith("//"):
            normalized = normalized.replace("//", "/")
        return normalized

    @classmethod
    def _walk(
        cls,
        value: Any,
        *,
        parent_key: str | None,
    ) -> tuple[Any, int]:
        if isinstance(value, dict):
            total = 0
            output: dict[Any, Any] = {}

            for key, item in value.items():
                output_key = key

                # rgthree Power Lora Loader guarda los nombres como claves
                # dentro de inputs.loras.
                if isinstance(key, str) and cls._should_normalize_dict_key(
                    parent_key=parent_key,
                    key=key,
                ):
                    output_key = cls._normalize_path(key)
                    total += int(output_key != key)

                normalized_item, count = cls._walk(
                    item,
                    parent_key=str(output_key),
                )
                output[output_key] = normalized_item
                total += count

            return output, total

        if isinstance(value, list):
            total = 0
            output_list: list[Any] = []
            for item in value:
                normalized_item, count = cls._walk(
                    item,
                    parent_key=parent_key,
                )
                output_list.append(normalized_item)
                total += count
            return output_list, total

        if isinstance(value, tuple):
            total = 0
            output_tuple: list[Any] = []
            for item in value:
                normalized_item, count = cls._walk(
                    item,
                    parent_key=parent_key,
                )
                output_tuple.append(normalized_item)
                total += count
            return tuple(output_tuple), total

        if isinstance(value, str) and cls._should_normalize_value(
            parent_key,
            value,
        ):
            normalized = cls._normalize_path(value)
            return normalized, int(normalized != value)

        return value, 0

    @classmethod
    def _should_normalize_dict_key(
        cls,
        *,
        parent_key: str | None,
        key: str,
    ) -> bool:
        if "\\" not in key:
            return False

        normalized_parent = str(parent_key or "").strip().lower()
        if normalized_parent in {"lora", "loras", "models", "checkpoints"}:
            return True

        return bool(cls._MODEL_EXTENSION.search(key))

    @classmethod
    def _should_normalize_value(
        cls,
        key: str | None,
        value: str,
    ) -> bool:
        if "\\" not in value:
            return False

        normalized_key = str(key or "").strip().lower()
        if (
            normalized_key in cls._PATH_KEYS
            or cls._PATH_KEY_PATTERN.search(normalized_key)
        ):
            return True

        if cls._WINDOWS_ABSOLUTE.match(value) or cls._UNC_PATH.match(value):
            return True

        return bool(cls._MODEL_EXTENSION.search(value))

    @classmethod
    def assert_no_windows_model_paths(
        cls,
        prompt: dict[str, Any],
    ) -> None:
        invalid: list[str] = []

        def visit(value: Any) -> None:
            if isinstance(value, dict):
                for key, item in value.items():
                    if (
                        isinstance(key, str)
                        and "\\" in key
                        and cls._MODEL_EXTENSION.search(key)
                    ):
                        invalid.append(key)
                    visit(item)
                return

            if isinstance(value, (list, tuple)):
                for item in value:
                    visit(item)
                return

            if (
                isinstance(value, str)
                and "\\" in value
                and cls._MODEL_EXTENSION.search(value)
            ):
                invalid.append(value)

        visit(prompt)

        if invalid:
            unique = ", ".join(sorted(set(invalid))[:10])
            raise ValueError(
                "The ComfyUI prompt still contains Windows model paths: "
                f"{unique}"
            )


comfyui_prompt_preprocessor_service = ComfyUIPromptPreprocessorService()
