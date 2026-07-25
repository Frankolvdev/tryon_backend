from app.services.comfyui_prompt_preprocessor_service import (
    comfyui_prompt_preprocessor_service,
)


def test_normalizes_model_and_file_paths_without_touching_prompt_text():
    prompt = {
        "1": {
            "class_type": "Power Lora Loader (rgthree)",
            "inputs": {
                "lora_name": r"Klein\model.safetensors",
                "prompt": r"A black\white dress",
            },
        },
        "2": {
            "class_type": "LoadImage",
            "inputs": {
                "image": r"uploads\person.png",
            },
        },
    }

    result = comfyui_prompt_preprocessor_service.preprocess(prompt)

    assert result["1"]["inputs"]["lora_name"] == "Klein/model.safetensors"
    assert result["2"]["inputs"]["image"] == "uploads/person.png"
    assert result["1"]["inputs"]["prompt"] == r"A black\white dress"


def test_normalizes_nested_unknown_key_when_value_is_an_obvious_windows_path():
    prompt = {
        "1": {
            "inputs": {
                "custom_value": r"C:\models\loras\model.safetensors",
            },
        },
    }

    result = comfyui_prompt_preprocessor_service.preprocess(prompt)

    assert (
        result["1"]["inputs"]["custom_value"]
        == "C:/models/loras/model.safetensors"
    )


def test_does_not_mutate_original_prompt():
    prompt = {"1": {"inputs": {"lora_name": r"A\B\model.safetensors"}}}

    result = comfyui_prompt_preprocessor_service.preprocess(prompt)

    assert prompt["1"]["inputs"]["lora_name"] == r"A\B\model.safetensors"
    assert result["1"]["inputs"]["lora_name"] == "A/B/model.safetensors"
