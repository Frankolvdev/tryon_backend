from __future__ import annotations

from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
BUILDER = ROOT / "app" / "services" / "runtime_builder_service.py"
CONTEXT = ROOT / "app" / "services" / "runtime_context_generator_service.py"


def read(path: Path) -> str:
    if not path.is_file():
        raise RuntimeError(f"No se encontró: {path}")
    return path.read_text(encoding="utf-8")


def backup(path: Path) -> None:
    destination = path.with_suffix(path.suffix + ".before_megazip_14b.bak")
    if not destination.exists():
        shutil.copy2(path, destination)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise RuntimeError(f"No se encontró el ancla: {label}")
    return text.replace(old, new, 1)


def patch_builder() -> None:
    text = read(BUILDER)
    backup(BUILDER)

    text = replace_once(
        text,
        '    DEFAULT_MODAL_VOLUME_PATH = "/models"\n',
        '''    DEFAULT_MODAL_VOLUME_PATH = "/models"

    # Integración aislada: solo se consume en runtimes Modal.
    DEFAULT_RUNTIME_ENGINE_REPOSITORY = (
        "https://github.com/Frankolvdev/comfyui_runtime_engine.git"
    )
    DEFAULT_RUNTIME_ENGINE_REF = "main"
    DEFAULT_RUNTIME_ENGINE_INSTALL_PATH = "/opt/comfyui-runtime-engine"
    DEFAULT_MODAL_RESIDENT_MODELS = (
        "diffusion_models/realDream_klein9BV1.safetensors",
    )
''',
        "constantes del engine",
    )

    helper_anchor = '''    @staticmethod
    def _modal_app(volume_name: str, volume_path: str, runtime_name: str) -> str:
'''
    helper_block = '''    @staticmethod
    def _modal_runtime_engine_toml(volume_path: str) -> str:
        residents = "\\n".join(
            f'  "{item}",' for item in RuntimeBuilderService.DEFAULT_MODAL_RESIDENT_MODELS
        )
        return f"""[runtime]
mode = "embedded"
comfyui_path = "/app/ComfyUI"
host = "127.0.0.1"
port = 8188
startup_timeout_seconds = 900
strict_version = true
supported_versions = ["0.15"]

[embedded]
allow_simulation_only = false
extra_args = ["--disable-api-nodes"]
shutdown_grace_seconds = 5.0
ensure_workspace = true

[snapshot]
enabled = true
gpu_enabled = true
resident_models = [
{residents}
]

[residency]
model_roots = ["{volume_path}"]
strict = true
execution_reserve_gb = 8.0
warmup_workflow = "/app/runtime/modal-snapshot-warmup.json"
warmup_timeout_seconds = 900
warmup_inputs = []

sam3_source_model = "{volume_path}/sam3/sam3.pt"
sam3_expected_model = "models/sam3/sam3.pt"
sam3_link_mode = "symlink"
sam3_replace_existing = false

[snapshot_lifecycle]
provider = "modal"
state_path = "/tmp/comfy-runtime-snapshot-state.json"
audit_path = "/tmp/comfy-runtime-snapshot-audit.json"

[diagnostics]
json_events = true
event_log = "/tmp/comfy-runtime-events.jsonl"
"""

    @staticmethod
    def _modal_snapshot_warmup_workflow() -> str:
        return json.dumps(
            {
                "runtime-resident-unet": {
                    "class_type": "UNETLoader",
                    "inputs": {
                        "unet_name": "realDream_klein9BV1.safetensors",
                        "weight_dtype": "default",
                    },
                },
                "runtime-resident-sink": {
                    "class_type": "TryonSnapshotWarmupSink",
                    "inputs": {"value": ["runtime-resident-unet", 0]},
                },
            },
            indent=2,
            ensure_ascii=False,
        )

    @staticmethod
    def _modal_app(volume_name: str, volume_path: str, runtime_name: str) -> str:
'''
    text = replace_once(text, helper_anchor, helper_block, "helpers Modal")

    text = replace_once(
        text,
        "from pathlib import Path\nimport modal\n",
        "from pathlib import Path\nimport modal\nfrom comfyui_runtime_engine.modal import ModalSnapshotAdapter\n",
        "import del adaptador",
    )

    constants_anchor = '''EXECUTION_TIMEOUT = int(os.getenv("TRYON_MODAL_EXECUTION_TIMEOUT", "1800"))
COMFYUI_ROOT = Path("/app/ComfyUI")
'''
    constants_block = '''EXECUTION_TIMEOUT = int(os.getenv("TRYON_MODAL_EXECUTION_TIMEOUT", "1800"))
RUNTIME_ENGINE_ENABLED = os.getenv(
    "TRYON_MODAL_RUNTIME_ENGINE_ENABLED", "true"
).strip().lower() in {{"1", "true", "yes", "on"}}
RUNTIME_ENGINE_CONFIG = Path(os.getenv(
    "TRYON_MODAL_RUNTIME_ENGINE_CONFIG", "/app/runtime/runtime-engine.toml"
))
RUNTIME_ENGINE_READY_PATH = Path(os.getenv(
    "TRYON_MODAL_RUNTIME_ENGINE_READY_PATH", "/tmp/comfy-runtime-modal-ready.json"
))
RUNTIME_ENGINE_RESTORE_PATH = Path(os.getenv(
    "TRYON_MODAL_RUNTIME_ENGINE_RESTORE_PATH", "/tmp/comfy-runtime-modal-restore.json"
))
RUNTIME_ENGINE_LOG_PATH = Path(os.getenv(
    "TRYON_MODAL_RUNTIME_ENGINE_LOG_PATH", "/tmp/comfy-runtime-modal.log"
))
COMFYUI_ROOT = Path("/app/ComfyUI")
'''
    text = replace_once(text, constants_anchor, constants_block, "config Modal")

    init_old = '''    @modal.enter(snap=True)
    def initialize_for_snapshot(self) -> None:
        _modal_trace(
            "container_snapshot_initialize",
            role="pipeline_server",
            snapshot_mode="comfyui_gpu_warm_snapshot",
            comfyui_started=False,
            models_loaded=False,
        )
        os.environ["RUNTIME_PROVIDER"] = "modal"
        os.environ["COMFYUI_PORT"] = str(COMFYUI_PORT)
        print("[modal] Iniciando ComfyUI antes del snapshot de memoria.", flush=True)
        self._start_process()
        _run_snapshot_model_warmup()
        _modal_trace(
            "container_snapshot_ready",
            role="pipeline_server",
            snapshot_mode="comfyui_gpu_warm_snapshot",
            comfyui_started=True,
            models_loaded=True,
            gpu=_diagnostic_gpu_state(),
        )
        print(
            "[modal] ComfyUI y modelos preparados; creando snapshot CPU+GPU.",
            flush=True,
        )
'''
    init_new = '''    @modal.enter(snap=True)
    def initialize_for_snapshot(self) -> None:
        _modal_trace(
            "container_snapshot_initialize",
            role="pipeline_server",
            snapshot_mode=(
                "runtime_engine_gpu_snapshot"
                if RUNTIME_ENGINE_ENABLED
                else "comfyui_gpu_warm_snapshot"
            ),
            comfyui_started=False,
            models_loaded=False,
            runtime_engine_enabled=RUNTIME_ENGINE_ENABLED,
        )
        os.environ["RUNTIME_PROVIDER"] = "modal"
        os.environ["COMFYUI_PORT"] = str(COMFYUI_PORT)

        if RUNTIME_ENGINE_ENABLED:
            _prepare_runtime_directories()
            _write_snapshot_warmup_node()
            self.snapshot_adapter = ModalSnapshotAdapter(
                config_path=RUNTIME_ENGINE_CONFIG,
                host="127.0.0.1",
                port=COMFYUI_PORT,
                startup_timeout_seconds=STARTUP_TIMEOUT,
                ready_path=RUNTIME_ENGINE_READY_PATH,
                restore_path=RUNTIME_ENGINE_RESTORE_PATH,
                log_path=RUNTIME_ENGINE_LOG_PATH,
            )
            report = self.snapshot_adapter.prepare_snapshot()
            self.comfyui_process = self.snapshot_adapter.process
            _modal_trace(
                "container_snapshot_ready",
                role="pipeline_server",
                snapshot_mode="runtime_engine_gpu_snapshot",
                comfyui_started=True,
                models_loaded=True,
                runtime_engine_health=report,
                gpu=_diagnostic_gpu_state(),
            )
            print("[modal] Runtime engine snapshot-ready; creando snapshot CPU+GPU.", flush=True)
            return

        print("[modal] Iniciando ComfyUI antes del snapshot de memoria.", flush=True)
        self._start_process()
        _run_snapshot_model_warmup()
        _modal_trace(
            "container_snapshot_ready",
            role="pipeline_server",
            snapshot_mode="comfyui_gpu_warm_snapshot",
            comfyui_started=True,
            models_loaded=True,
            runtime_engine_enabled=False,
            gpu=_diagnostic_gpu_state(),
        )
        print("[modal] ComfyUI y modelos preparados; creando snapshot CPU+GPU.", flush=True)
'''
    text = replace_once(text, init_old, init_new, "snap=True")

    restore_old = '''    @modal.enter(snap=False)
    def restore_after_snapshot(self) -> None:
        _modal_trace(
            "container_restore_start",
            role="pipeline_server",
            startup_mode="restored_comfyui_gpu_snapshot",
        )
        process = getattr(self, "comfyui_process", None)
'''
    restore_new = '''    @modal.enter(snap=False)
    def restore_after_snapshot(self) -> None:
        _modal_trace(
            "container_restore_start",
            role="pipeline_server",
            startup_mode=(
                "restored_runtime_engine_gpu_snapshot"
                if RUNTIME_ENGINE_ENABLED
                else "restored_comfyui_gpu_snapshot"
            ),
            runtime_engine_enabled=RUNTIME_ENGINE_ENABLED,
        )
        if RUNTIME_ENGINE_ENABLED:
            adapter = getattr(self, "snapshot_adapter", None)
            if adapter is None:
                raise RuntimeError("El snapshot no restauró ModalSnapshotAdapter.")
            report = adapter.after_restore()
            self.comfyui_process = adapter.process
            _modal_trace(
                "container_ready",
                role="pipeline_server",
                restored_from_snapshot=True,
                comfyui_snapshotted=True,
                models_snapshotted=True,
                startup_mode="restored_runtime_engine_gpu_snapshot",
                runtime_engine_health=report,
                gpu=_diagnostic_gpu_state(),
            )
            print("[modal] Runtime engine restaurado y validado.", flush=True)
            return

        process = getattr(self, "comfyui_process", None)
'''
    text = replace_once(text, restore_old, restore_new, "snap=False")

    docker_anchor = '''                    f"RUN git clone {config.comfyui_repository} /app/ComfyUI",
                    commit_line,
                    f"RUN python -m pip install --index-url {config.pytorch_index_url} torch torchvision torchaudio",
'''
    docker_block = '''                    f"RUN git clone {config.comfyui_repository} /app/ComfyUI",
                    commit_line,
                    ("ARG COMFY_RUNTIME_ENGINE_GIT_URL=" + RuntimeBuilderService.DEFAULT_RUNTIME_ENGINE_REPOSITORY) if modal_enabled else "",
                    ("ARG COMFY_RUNTIME_ENGINE_GIT_REF=" + RuntimeBuilderService.DEFAULT_RUNTIME_ENGINE_REF) if modal_enabled else "",
                    ("RUN git clone --filter=blob:none ${COMFY_RUNTIME_ENGINE_GIT_URL} " + RuntimeBuilderService.DEFAULT_RUNTIME_ENGINE_INSTALL_PATH + " && git -C " + RuntimeBuilderService.DEFAULT_RUNTIME_ENGINE_INSTALL_PATH + " checkout ${COMFY_RUNTIME_ENGINE_GIT_REF}") if modal_enabled else "",
                    ("RUN python -m pip install --no-cache-dir " + RuntimeBuilderService.DEFAULT_RUNTIME_ENGINE_INSTALL_PATH) if modal_enabled else "",
                    f"RUN python -m pip install --index-url {config.pytorch_index_url} torch torchvision torchaudio",
'''
    text = replace_once(text, docker_anchor, docker_block, "Dockerfile builder")

    result_anchor = '''        if modal_enabled:
            volume_name = str(modal_volume_name or "").strip()
'''
    result_block = '''        if modal_enabled:
            result["modal_runtime_engine_toml"] = RuntimeBuilderService._modal_runtime_engine_toml(volume_path)
            result["modal_snapshot_warmup_workflow"] = RuntimeBuilderService._modal_snapshot_warmup_workflow()
            volume_name = str(modal_volume_name or "").strip()
'''
    text = replace_once(text, result_anchor, result_block, "result Modal")

    BUILDER.write_text(text, encoding="utf-8", newline="\n")


def patch_context() -> None:
    text = read(CONTEXT)
    backup(CONTEXT)

    files_anchor = '''            "tryon_runtime_guard/__init__.py": generated["tryon_runtime_guard"],
        }
'''
    files_block = '''            "tryon_runtime_guard/__init__.py": generated["tryon_runtime_guard"],
        }
        if generated.get("modal_runtime_engine_toml"):
            files["runtime-engine.toml"] = generated["modal_runtime_engine_toml"]
        if generated.get("modal_snapshot_warmup_workflow"):
            files["modal-snapshot-warmup.json"] = generated["modal_snapshot_warmup_workflow"]
'''
    text = replace_once(text, files_anchor, files_block, "archivos contexto")

    docker_anchor = '''            f"RUN git clone {config.comfyui_repository} {comfy_target}",
        ]
'''
    docker_block = '''            f"RUN git clone {config.comfyui_repository} {comfy_target}",
        ]
        if modal_enabled:
            lines += [
                "ARG COMFY_RUNTIME_ENGINE_GIT_URL=" + RuntimeBuilderService.DEFAULT_RUNTIME_ENGINE_REPOSITORY,
                "ARG COMFY_RUNTIME_ENGINE_GIT_REF=" + RuntimeBuilderService.DEFAULT_RUNTIME_ENGINE_REF,
                "RUN git clone --filter=blob:none ${COMFY_RUNTIME_ENGINE_GIT_URL} " + RuntimeBuilderService.DEFAULT_RUNTIME_ENGINE_INSTALL_PATH + " && git -C " + RuntimeBuilderService.DEFAULT_RUNTIME_ENGINE_INSTALL_PATH + " checkout ${COMFY_RUNTIME_ENGINE_GIT_REF}",
                "RUN python -m pip install --no-cache-dir " + RuntimeBuilderService.DEFAULT_RUNTIME_ENGINE_INSTALL_PATH,
                "COPY runtime-engine.toml /app/runtime/runtime-engine.toml",
                "COPY modal-snapshot-warmup.json /app/runtime/modal-snapshot-warmup.json",
            ]
'''
    text = replace_once(text, docker_anchor, docker_block, "Dockerfile contexto")

    required_anchor = '''                'from generation_runtime import GenerationRuntime',
            )
'''
    required_block = '''                'from generation_runtime import GenerationRuntime',
                'from comfyui_runtime_engine.modal import ModalSnapshotAdapter',
                'TRYON_MODAL_RUNTIME_ENGINE_ENABLED',
                'snapshot_adapter.prepare_snapshot()',
                'adapter.after_restore()',
            )
'''
    text = replace_once(text, required_anchor, required_block, "validación modal_app")

    CONTEXT.write_text(text, encoding="utf-8", newline="\n")


def verify() -> None:
    builder = read(BUILDER)
    context = read(CONTEXT)
    checks = (
        (builder, "DEFAULT_RUNTIME_ENGINE_REPOSITORY"),
        (builder, "ModalSnapshotAdapter"),
        (builder, "snapshot_adapter.prepare_snapshot()"),
        (builder, "adapter.after_restore()"),
        (builder, "_modal_runtime_engine_toml"),
        (context, 'files["runtime-engine.toml"]'),
        (context, 'files["modal-snapshot-warmup.json"]'),
        (context, "COMFY_RUNTIME_ENGINE_GIT_URL"),
    )
    missing = [needle for haystack, needle in checks if needle not in haystack]
    if missing:
        raise RuntimeError(f"Verificación incompleta: {missing}")


def main() -> int:
    patch_builder()
    patch_context()
    verify()
    print("MegaZIP 14B aplicado y verificado.")
    print("Modificados:")
    print(" - app/services/runtime_builder_service.py")
    print(" - app/services/runtime_context_generator_service.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
