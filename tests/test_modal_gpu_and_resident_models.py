from app.services.runtime_builder_service import RuntimeBuilderService


def test_configurable_modal_residents_include_clip_and_unet_alias():
    residents = [
        "diffusion_models/realDream_klein9BV1.safetensors",
        "text_encoders/qwen_3_8b.safetensors",
        "unet/Flux2-Klein-9B-True-v2-bf16.safetensors",
    ]
    config = RuntimeBuilderService._modal_runtime_engine_toml("/models", residents)
    warmup = RuntimeBuilderService._modal_snapshot_warmup_workflow(residents)
    assert all(model in config for model in residents)
    assert '"class_type": "CLIPLoader"' in warmup
    assert warmup.count('"class_type": "UNETLoader"') == 2
    assert "Flux2-Klein-9B-True-v2-bf16.safetensors" in warmup
