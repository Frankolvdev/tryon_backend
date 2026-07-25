from app.services.comfyui_prompt_preprocessor_service import (
    comfyui_prompt_preprocessor_service,
)


def test_normalizes_rgthree_lora_dictionary_keys():
    prompt = {
        "100": {
            "class_type": "Power Lora Loader (rgthree)",
            "inputs": {
                "loras": {
                    r"Klein\bfs_head_v1_flux-klein_9b_step3500_rank128.safetensors": {
                        "on": True,
                        "strength": 1.0,
                    },
                    r"Klein\lenovo_flux_klein9b.safetensors": {
                        "on": True,
                        "strength": 0.8,
                    },
                }
            },
        }
    }

    normalized = comfyui_prompt_preprocessor_service.preprocess(prompt)
    loras = normalized["100"]["inputs"]["loras"]

    assert "Klein/bfs_head_v1_flux-klein_9b_step3500_rank128.safetensors" in loras
    assert "Klein/lenovo_flux_klein9b.safetensors" in loras
    comfyui_prompt_preprocessor_service.assert_no_windows_model_paths(normalized)


def test_normalizes_regular_lora_values():
    prompt = {
        "1": {
            "inputs": {
                "lora_name": r"Klein\f2k_consis.safetensors",
            }
        }
    }
    normalized = comfyui_prompt_preprocessor_service.preprocess(prompt)
    assert normalized["1"]["inputs"]["lora_name"] == "Klein/f2k_consis.safetensors"


def test_preserves_free_prompt_text():
    prompt = {
        "1": {
            "inputs": {
                "text": r"Una escena que contiene texto C:\ejemplo sin archivo",
            }
        }
    }
    normalized = comfyui_prompt_preprocessor_service.preprocess(prompt)
    assert normalized == prompt
