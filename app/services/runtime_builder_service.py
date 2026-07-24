import json
import re
from dataclasses import asdict, dataclass
from typing import Any

from app.models.runtime_builder_config import RuntimeBuilderConfig


@dataclass
class ValidationIssue:
    level: str
    field: str
    message: str


class RuntimeBuilderService:
    """Validate and generate reproducible ComfyUI runtimes.

    This keeps the existing workflow/custom-node/model discovery flow intact.  The
    only dependency change is a conservative renderer that preserves PEP 508
    extras and markers instead of blindly inserting ``==``.
    """

    DEFAULT_MODAL_VOLUME_PATH = "/app/ComfyUI/models"


    PROTECTED_GPU_PACKAGES = {
        "torch", "torchvision", "torchaudio", "xformers", "triton",
        "onnxruntime-gpu", "flash-attn",
    }

    # Single source of truth used by the API endpoint, validation and exports.
    # MEGA31 accidentally removed this class attribute while the endpoint still
    # referenced it, causing GET /runtime-builder/config to fail at runtime.
    RECOMMENDED_PROFILE = {
        "id": "universal-modal-rtx5090",
        "label": "Universal GPU — Modal + RTX 5090",
        "python_version": "3.11",
        "cuda_version": "12.8.1",
        "pytorch_index_url": "https://download.pytorch.org/whl/cu128",
        "comfyui_version": "0.15.1",
        "comfyui_frontend_version": "1.39.19",
        "comfyui_commit": "3dd10a59c00248d00f0cb0ab794ff1bb9fb00a5f",
    }

    # Nombres alternativos de carpetas locales. El exportador siempre copia la
    # instalación local y nunca descarga ni reemplaza Custom Nodes desde Git.
    CUSTOM_NODE_ALIASES = {
        "comfyui-execute-python": ("execute-python",),
        "was-node-suite-comfyui": ("was-ns",),
        "comfyliterals": ("comfy-literals", "comfyui-comfyliterals"),
    }

    REQUIRED_CUSTOM_NODES = (
        {"name": "ComfyUI-Manager", "repository": "https://github.com/Comfy-Org/ComfyUI-Manager.git", "commit": None, "enabled": True, "install_requirements": True, "required_by_default": True},
        {"name": "rgthree-comfy", "repository": "https://github.com/rgthree/rgthree-comfy.git", "commit": None, "enabled": True, "install_requirements": True, "required_by_default": True},
        {"name": "ComfyUI-Easy-Use", "repository": "https://github.com/yolain/ComfyUI-Easy-Use.git", "commit": None, "enabled": True, "install_requirements": True, "required_by_default": True},
        {"name": "ComfyUI-Lora-Manager", "repository": "https://github.com/willmiao/ComfyUI-Lora-Manager.git", "commit": None, "enabled": True, "install_requirements": True, "required_by_default": True},
        {"name": "ComfyUI-KJNodes", "repository": "https://github.com/kijai/ComfyUI-KJNodes.git", "commit": None, "enabled": True, "install_requirements": True, "required_by_default": True},
        {"name": "ComfyUI_essentials", "repository": "https://github.com/cubiq/ComfyUI_essentials.git", "commit": None, "enabled": True, "install_requirements": True, "required_by_default": True},
        {"name": "was-node-suite-comfyui", "repository": "https://github.com/WASasquatch/was-node-suite-comfyui.git", "commit": None, "enabled": True, "install_requirements": True, "required_by_default": True},
        {"name": "ComfyUI-Logic", "repository": "https://github.com/theUpsider/ComfyUI-Logic.git", "commit": None, "enabled": True, "install_requirements": True, "required_by_default": True},
        {"name": "ComfyUI-Execute-Python", "repository": "https://github.com/mozhaa/ComfyUI-Execute-Python.git", "commit": None, "enabled": True, "install_requirements": True, "required_by_default": True},
        {"name": "ComfyLiterals", "repository": "https://github.com/M1kep/ComfyLiterals.git", "commit": None, "enabled": True, "install_requirements": True, "required_by_default": True},
        {"name": "Anomalous_Model_Browser", "repository": "https://github.com/DemonGatanjieu/Anomalous_Model_Browser.git", "commit": None, "enabled": True, "install_requirements": True, "required_by_default": True},
    )

    @staticmethod
    def sanitize_runtime_name(value: str | None) -> str:
        import unicodedata
        normalized = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii").lower()
        normalized = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
        normalized = re.sub(r"-+", "-", normalized)[:120].rstrip("-")
        if not normalized:
            normalized = "generation-runtime"
        if not normalized[0].isalpha():
            normalized = f"runtime-{normalized}"
        return normalized

    @staticmethod
    def merge_required_custom_nodes(nodes: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = [dict(item) for item in RuntimeBuilderService.REQUIRED_CUSTOM_NODES]
        keys = {str(item["repository"]).lower().removesuffix(".git") for item in merged}
        for item in nodes or []:
            repo = str(item.get("repository") or "").lower().removesuffix(".git")
            name = str(item.get("name") or "").lower()
            if repo in keys or any(str(x.get("name") or "").lower() == name for x in merged):
                continue
            merged.append(dict(item))
            if repo:
                keys.add(repo)
        return merged

    DEVELOPMENT_DEPENDENCIES = {
        "black", "flake8", "pytest", "pytest-cov", "pytest-asyncio",
        "coverage", "ruff", "isort", "mypy", "pre-commit", "tox",
        "nox", "bandit", "pylint", "autopep8", "yapf",
    }

    @staticmethod
    def _requirement_name(requirement: str) -> str:
        value = str(requirement or "").strip()
        value = value.split(";", 1)[0].strip()
        return re.split(r"\[|===|==|~=|!=|<=|>=|<|>|\s", value, maxsplit=1)[0].strip().lower()

    @staticmethod
    def is_runtime_dependency(requirement: str) -> bool:
        name = RuntimeBuilderService._requirement_name(requirement)
        return name not in RuntimeBuilderService.DEVELOPMENT_DEPENDENCIES and name not in RuntimeBuilderService.PROTECTED_GPU_PACKAGES

    @staticmethod
    def normalize_cuda_version(value: str | None) -> str:
        version = str(value or "").strip()
        if re.fullmatch(r"\d+\.\d+", version):
            return f"{version}.0"
        if re.fullmatch(r"\d+\.\d+\.\d+", version):
            return version
        raise ValueError(
            "La versión CUDA debe usar el formato mayor.menor o mayor.menor.parche, "
            "por ejemplo 12.8 o 12.8.0."
        )

    @staticmethod
    def _dependency_source(dependency: dict[str, Any]) -> str:
        return str(
            dependency.get("requirement")
            or dependency.get("package")
            or dependency.get("name")
            or ""
        ).strip()

    @staticmethod
    def render_requirement(dependency: dict[str, Any]) -> str:
        """Render one dependency as a valid PEP 508 requirement.

        Existing scanner output is accepted in either of these forms:
        - package=qrcode, version=[pil]       -> qrcode[pil]
        - package=onnxruntime-gpu, version="; marker" -> package; marker
        - package already containing extras/markers/specifier -> preserved
        - ordinary package + version -> package==version
        """

        raw_package = RuntimeBuilderService._dependency_source(dependency)
        raw_version = str(dependency.get("version") or "").strip()
        if not raw_package:
            raise ValueError("La dependencia no contiene package, name o requirement.")

        # mediapipe 0.10.0 no publica una distribución instalable para el
        # entorno Linux/Python usado por el runtime. 0.10.21 conserva la API
        # clásica utilizada por los Custom Nodes y sí dispone de wheels.
        package_name = raw_package.strip().lower()
        if package_name == "mediapipe" and raw_version in {"0.10.0", "==0.10.0"}:
            raw_version = "0.10.21"
        # PyAV 9.0.0 no ofrece wheel compatible con el runtime Linux/Python 3.10
        # y obliga a compilar contra FFmpeg, donde falla con toolchains actuales.
        # 12.3.0 mantiene la API usada por los nodos y dispone de wheels manylinux.
        if package_name == "av":
            version_number = raw_version.removeprefix("==").strip()
            if re.fullmatch(r"(?:8|9|10|11)(?:\.\d+){0,2}", version_number):
                raw_version = "12.3.0"

        # Some imported requirements already contain the whole PEP 508 string.
        if dependency.get("requirement"):
            candidate = raw_package
        elif raw_version.startswith("[") and raw_version.endswith("]"):
            # Fixes qrcode==[pil] generated by the previous renderer.
            candidate = f"{raw_package}{raw_version}"
        elif raw_version.startswith(";"):
            # Fixes onnxruntime-gpu==; marker.
            candidate = f"{raw_package}{raw_version}"
        elif not raw_version:
            candidate = raw_package
        elif re.match(r"^(===|==|~=|!=|<=|>=|<|>)", raw_version):
            candidate = f"{raw_package}{raw_version}"
        else:
            candidate = f"{raw_package}=={raw_version}"

        # Validación conservadora sin dependencias externas. El Runtime Builder
        # solo necesita impedir las formas que él mismo podía generar mal.
        if not candidate or candidate.startswith(("==", ";", "[")):
            raise ValueError(f"Dependencia Python inválida: {candidate!r}.")
        if "==[" in candidate or "==;" in candidate:
            raise ValueError(f"Dependencia Python inválida: {candidate!r}.")
        if any(char in candidate for char in ("\n", "\r", "\x00")):
            raise ValueError(f"Dependencia Python inválida: {candidate!r}.")
        return candidate

    @staticmethod
    def render_requirements(dependencies: list[dict[str, Any]]) -> list[str]:
        rendered: list[str] = []
        seen: set[str] = set()
        for dependency in dependencies:
            requirement = RuntimeBuilderService.render_requirement(dependency)
            if not RuntimeBuilderService.is_runtime_dependency(requirement):
                continue
            key = requirement.lower()
            if key not in seen:
                seen.add(key)
                rendered.append(requirement)
        return rendered

    @staticmethod
    def _is_modal(config: RuntimeBuilderConfig) -> bool:
        # Compatibilidad con configuraciones anteriores: todavía no existe un
        # selector visual de proveedor. Modal se detecta por plataforma/notas,
        # variables de entorno o por la existencia del Volume de modelos.
        values = [
            str(getattr(config, "target_platform", "") or ""),
            str(getattr(config, "notes", "") or ""),
        ]
        for item in getattr(config, "environment_variables", None) or []:
            values.extend([str(item.get("key") or ""), str(item.get("value") or "")])
        for volume in getattr(config, "volumes", None) or []:
            values.extend([
                str(volume.get("name") or ""),
                str(volume.get("mount_path") or volume.get("container_path") or volume.get("path") or ""),
            ])
        if any("modal" in value.lower() for value in values):
            return True

        # En el Runtime Builder actual, un Volume configurado junto con modelos
        # de estrategia volume representa el almacenamiento externo de Modal.
        # Esto evita depender de un campo de proveedor que aún no existe en UI.
        return bool(getattr(config, "volumes", None)) and RuntimeBuilderService._models_are_external(config)

    @staticmethod
    def _models_are_external(config: RuntimeBuilderConfig) -> bool:
        enabled = [item for item in (config.models or []) if item.get("enabled", True)]
        if not enabled:
            return False
        external_strategies = {"volume", "external-volume", "external_volume", "mounted"}
        return all(str(item.get("strategy") or "").lower() in external_strategies for item in enabled)

    @staticmethod
    def _modal_volume_path(config: RuntimeBuilderConfig) -> str:
        for volume in config.volumes or []:
            provider = str(volume.get("provider") or volume.get("type") or "").lower()
            if provider == "modal" or str(volume.get("name") or "").lower().startswith("modal"):
                configured = str(
                    volume.get("container_path")
                    or volume.get("mount_path")
                    or volume.get("path")
                    or RuntimeBuilderService.DEFAULT_MODAL_VOLUME_PATH
                ).rstrip("/")
                if configured in {"/app/ComfyUI/models", "/models"}:
                    return RuntimeBuilderService.DEFAULT_MODAL_VOLUME_PATH
                return configured
        return RuntimeBuilderService.DEFAULT_MODAL_VOLUME_PATH

    @staticmethod
    def _extra_model_paths_yaml(base_path: str) -> str:
        return "\n".join(
            [
                "tryon_modal_volume:",
                f"  base_path: {base_path}",
                "  checkpoints: checkpoints",
                "  clip: clip",
                "  clip_vision: clip_vision",
                "  configs: configs",
                "  controlnet: controlnet",
                "  diffusion_models: diffusion_models",
                "  embeddings: embeddings",
                "  gligen: gligen",
                "  hypernetworks: hypernetworks",
                "  loras: loras",
                "  photomaker: photomaker",
                "  style_models: style_models",
                "  text_encoders: text_encoders",
                "  upscale_models: upscale_models",
                "  vae: vae",
                "  vae_approx: vae_approx",
                "",
            ]
        )

    @staticmethod
    def _modal_app(volume_name: str, volume_path: str, runtime_name: str) -> str:
        # Modal builds directly from the generated Dockerfile. GPU snapshots stay
        # opt-in because the feature remains experimental and must be benchmarked.
        return f'''import modal

APP_NAME = {json.dumps(runtime_name)}
VOLUME_NAME = {json.dumps(volume_name)}
VOLUME_PATH = {json.dumps(volume_path)}

app = modal.App(APP_NAME)
models_volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)
image = modal.Image.from_dockerfile("Dockerfile")

@app.function(
    image=image,
    gpu=["L40S", "A100-80GB", "H100"],
    volumes={{VOLUME_PATH: models_volume}},
    timeout=1800,
    scaledown_window=60,
    enable_memory_snapshot=True,
    experimental_options={{"enable_gpu_snapshot": True}},
)
@modal.web_server(8000, startup_timeout=600)
def comfyui():
    import subprocess

    subprocess.Popen([
        "/app/runtime/scripts/startup.sh",
    ])
'''

    @staticmethod
    def validate(config: RuntimeBuilderConfig) -> dict:
        issues: list[ValidationIssue] = []
        runtime_name = RuntimeBuilderService.sanitize_runtime_name(getattr(config, "runtime_name", None))
        if runtime_name != str(getattr(config, "runtime_name", "") or ""):
            issues.append(ValidationIssue("error", "runtime_name", f"El nombre debe usar formato Docker seguro. Sugerencia: {runtime_name}"))
        if not str(config.pytorch_index_url).rstrip("/").endswith("cu128"):
            issues.append(ValidationIssue("warning", "pytorch_index_url", "Para compatibilidad amplia con RTX 5090 y Modal se recomienda el índice cu128."))
        if RuntimeBuilderService.normalize_cuda_version(config.cuda_version) < "12.8.0":
            issues.append(ValidationIssue("warning", "cuda_version", "Para RTX 5090 se recomienda CUDA 12.8 o superior."))
        if not config.comfyui_commit:
            issues.append(
                ValidationIssue(
                    "warning",
                    "comfyui_commit",
                    "Conviene fijar un commit de ComfyUI para builds reproducibles.",
                )
            )
        if ":" not in config.registry_image:
            issues.append(
                ValidationIssue(
                    "warning",
                    "registry_image",
                    "La imagen no contiene un tag explícito; se agregará la versión del runtime.",
                )
            )
        if not re.match(r"^\d+\.\d+\.\d+([-.][A-Za-z0-9.]+)?$", config.runtime_version):
            issues.append(
                ValidationIssue(
                    "error",
                    "runtime_version",
                    "La versión debe seguir un formato semántico, por ejemplo 1.0.0.",
                )
            )

        names: set[str] = set()
        for index, node in enumerate(RuntimeBuilderService.merge_required_custom_nodes(config.custom_nodes)):
            name = str(node.get("name", "")).strip().lower()
            if not node.get("enabled", True):
                continue
            if name in names:
                issues.append(
                    ValidationIssue(
                        "error",
                        f"custom_nodes.{index}.name",
                        "Existe un custom node duplicado.",
                    )
                )
            names.add(name)
            if not str(node.get("repository", "")).startswith(("https://", "git@")):
                issues.append(
                    ValidationIssue(
                        "error",
                        f"custom_nodes.{index}.repository",
                        "El repositorio del nodo no es válido.",
                    )
                )
            if not node.get("commit"):
                issues.append(
                    ValidationIssue(
                        "warning",
                        f"custom_nodes.{index}.commit",
                        "El nodo no tiene commit fijo.",
                    )
                )

        enabled_models = [item for item in (config.models or []) if item.get("enabled", True)]
        for index, model in enumerate(enabled_models):
            if model.get("strategy") in {"image", "startup-download"} and not model.get("source_url"):
                issues.append(
                    ValidationIssue(
                        "error",
                        f"models.{index}.source_url",
                        "El modelo necesita una URL para esta estrategia.",
                    )
                )
            sha = model.get("sha256")
            if sha and not re.fullmatch(r"[a-fA-F0-9]{64}", sha):
                issues.append(
                    ValidationIssue(
                        "error",
                        f"models.{index}.sha256",
                        "SHA-256 debe contener 64 caracteres hexadecimales.",
                    )
                )

        for index, dependency in enumerate(config.python_dependencies or []):
            if not dependency.get("enabled", True):
                continue
            try:
                RuntimeBuilderService.render_requirement(dependency)
            except ValueError as exc:
                issues.append(
                    ValidationIssue(
                        "error",
                        f"python_dependencies.{index}",
                        str(exc),
                    )
                )

        if RuntimeBuilderService._is_modal(config) and RuntimeBuilderService._models_are_external(config):
            if not config.volumes:
                issues.append(
                    ValidationIssue(
                        "error",
                        "volumes",
                        "Modal con modelos externos necesita un Volume configurado.",
                    )
                )

        return {
            "valid": not any(issue.level == "error" for issue in issues),
            "issues": [asdict(issue) for issue in issues],
            "summary": {
                "custom_nodes": len(
                    [n for n in RuntimeBuilderService.merge_required_custom_nodes(config.custom_nodes) if n.get("enabled", True)]
                ),
                "models": len(enabled_models),
                "python_dependencies": len(
                    [d for d in (config.python_dependencies or []) if d.get("enabled", True)]
                ),
                "volumes": len(config.volumes or []),
                "reproducible": bool(config.comfyui_commit)
                and all(
                    bool(n.get("commit"))
                    for n in RuntimeBuilderService.merge_required_custom_nodes(config.custom_nodes)
                    if n.get("enabled", True)
                ),
            },
        }

    @staticmethod
    def generate(config: RuntimeBuilderConfig) -> dict:
        validation = RuntimeBuilderService.validate(config)
        if not validation["valid"]:
            errors = [item["message"] for item in validation["issues"] if item["level"] == "error"]
            raise ValueError("No se puede generar el runtime: " + " | ".join(errors))

        nodes = [n for n in RuntimeBuilderService.merge_required_custom_nodes(config.custom_nodes) if n.get("enabled", True)]
        deps = [d for d in (config.python_dependencies or []) if d.get("enabled", True)]
        models = [m for m in (config.models or []) if m.get("enabled", True)]

        node_lines: list[str] = []
        for node in nodes:
            folder = re.sub(r"[^A-Za-z0-9_.-]", "-", node["name"]).strip("-")
            node_lines.append(
                f"RUN git clone {node['repository']} /app/ComfyUI/custom_nodes/{folder}"
            )
            if node.get("commit"):
                node_lines.append(
                    f"RUN git -C /app/ComfyUI/custom_nodes/{folder} checkout {node['commit']}"
                )
            if node.get("install_requirements", True):
                node_lines.append(
                    "RUN if [ -f /app/ComfyUI/custom_nodes/"
                    f"{folder}/requirements.txt ]; then sed -Ei '/^(torch|torchvision|torchaudio|xformers|triton|onnxruntime-gpu|flash-attn)([<>=!~ ;]|$)/Id' "
                    f"/app/ComfyUI/custom_nodes/{folder}/requirements.txt && python -m pip install --no-cache-dir --constraint /tmp/runtime-constraints.txt -r "
                    f"/app/ComfyUI/custom_nodes/{folder}/requirements.txt; fi"
                )

        requirements = RuntimeBuilderService.render_requirements(deps)
        requirements_txt = "\n".join(requirements) + ("\n" if requirements else "")

        model_lines: list[str] = []
        for model in models:
            if model.get("strategy") == "image":
                model_lines.append(
                    "RUN mkdir -p $(dirname /app/ComfyUI/models/"
                    f"{model['target_path']}) && curl -fL '{model['source_url']}' "
                    f"-o /app/ComfyUI/models/{model['target_path']}"
                )

        modal_enabled = RuntimeBuilderService._is_modal(config)
        external_models = RuntimeBuilderService._models_are_external(config)
        volume_path = RuntimeBuilderService._modal_volume_path(config)
        extra_paths_copy = ""
        if modal_enabled and external_models:
            extra_paths_copy = "COPY runtime-builder/extra_model_paths.yaml /app/ComfyUI/extra_model_paths.yaml"

        commit_line = (
            f"RUN git -C /app/ComfyUI checkout {config.comfyui_commit}"
            if config.comfyui_commit
            else ""
        )
        dockerfile = "\n".join(
            filter(
                None,
                [
                    f"FROM nvidia/cuda:{RuntimeBuilderService.normalize_cuda_version(config.cuda_version)}-cudnn-runtime-ubuntu22.04",
                    'ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PATH="/opt/conda/bin:$PATH" TORCH_CUDA_ARCH_LIST="7.5;8.0;8.6;8.9;9.0;10.0;12.0"',
                    "RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates git curl bzip2 ffmpeg libgl1 libopengl0 libglib2.0-0 build-essential pkg-config libgeos-dev libgdal-dev libcairo2-dev libjpeg-dev libpng-dev libtiff-dev libavcodec-dev libavdevice-dev libavfilter-dev libavformat-dev libavutil-dev libswresample-dev libswscale-dev && rm -rf /var/lib/apt/lists/*",
                    "RUN geos-config --version && ldconfig -p | grep -F libgeos_c.so",
                    "RUN curl -fL https://github.com/conda-forge/miniforge/releases/download/26.3.2-3/Miniforge3-26.3.2-3-Linux-x86_64.sh -o /tmp/miniforge.sh && echo '848194851a98903134187fbb4ab50efe87b003e0c0f808f97644b7524a62bf2c  /tmp/miniforge.sh' | sha256sum -c - && bash /tmp/miniforge.sh -b -p /opt/conda && rm /tmp/miniforge.sh && conda install -y python=3.11 pip && conda clean -afy",
                    "RUN python --version && python -m pip install --upgrade 'pip>=25,<26' setuptools wheel",
                    f"RUN git clone {config.comfyui_repository} /app/ComfyUI",
                    commit_line,
                    f"RUN python -m pip install --index-url {config.pytorch_index_url} torch torchvision torchaudio",
                    "RUN printf '%s\\n' 'transformers>=4.50.3,<5' > /tmp/runtime-constraints.txt && sed -Ei 's/^transformers.*$/transformers>=4.50.3,<5/I; /^(torch|torchvision|torchaudio|xformers|triton|onnxruntime-gpu|flash-attn)([<>=!~ ;]|$)/Id' /app/ComfyUI/requirements.txt && python -m pip install --constraint /tmp/runtime-constraints.txt -r /app/ComfyUI/requirements.txt",
                    *node_lines,
                    "COPY runtime-builder/requirements.txt /tmp/runtime-requirements.txt",
                    "RUN if [ -s /tmp/runtime-requirements.txt ]; then python -m pip install --constraint /tmp/runtime-constraints.txt -r /tmp/runtime-requirements.txt; fi",
                    "RUN python -m pip check",
                    "RUN python -c 'import sys, torch, transformers; assert sys.version_info[:2] == (3, 11); assert torch.version.cuda and torch.version.cuda.startswith(\"12.8\"); assert int(transformers.__version__.split(\".\")[0]) < 5; print(sys.version); print(torch.__version__, torch.version.cuda); print(transformers.__version__)'",
                    *model_lines,
                    extra_paths_copy,
                    "COPY runpod_worker /app/runtime/runpod_worker",
                    "WORKDIR /app/runtime/runpod_worker",
                    "RUN python -m pip install --constraint /tmp/runtime-constraints.txt -r requirements.txt",
                    "COPY runtime-builder/entrypoint.sh /app/runtime/entrypoint.sh",
                    "RUN chmod +x /app/runtime/entrypoint.sh",
                    'ENTRYPOINT ["/app/runtime/entrypoint.sh"]',
                ],
            )
        ) + "\n"

        comfy_args = "--listen 0.0.0.0 --port 8000" if modal_enabled else "--listen 127.0.0.1 --port 8188"
        health_port = 8000 if modal_enabled else 8188
        entrypoint = f"""#!/usr/bin/env bash
set -euo pipefail
python /app/ComfyUI/main.py {comfy_args} &
COMFY_PID=$!
for _ in $(seq 1 600); do
  curl -fsS http://127.0.0.1:{health_port}/system_stats >/dev/null && break
  sleep 1
done
if [ -f /app/runtime/runpod_worker/handler.py ] && [ \"${{RUNTIME_PROVIDER:-}}\" != \"modal\" ]; then
  python /app/runtime/runpod_worker/handler.py
fi
wait $COMFY_PID
"""

        runtime_manifest = {
            "contract": "runtime-builder/v2",
            "runtime_name": RuntimeBuilderService.sanitize_runtime_name(config.runtime_name),
            "gpu_profile": "universal-cu128",
            "gpu_targets": ["RTX 5090", "L4", "L40S", "A10G", "A100", "H100", "H200"],
            "name": config.name,
            "version": config.runtime_version,
            "platform": config.target_platform,
            "registry_image": config.registry_image,
            "comfyui": {
                "repository": config.comfyui_repository,
                "commit": config.comfyui_commit,
                "version": RuntimeBuilderService.RECOMMENDED_PROFILE["comfyui_version"],
                "frontend_version": RuntimeBuilderService.RECOMMENDED_PROFILE["comfyui_frontend_version"],
            },
            "compatibility_profile": RuntimeBuilderService.RECOMMENDED_PROFILE,
            "python": config.python_version,
            "cuda": config.cuda_version,
            "volumes": config.volumes or [],
            "provider": "modal" if modal_enabled else "docker",
            "model_storage": "external-volume" if external_models else "bundled",
        }
        custom_nodes_lock = {"nodes": nodes}
        models_manifest = {"models": models}
        env_example = (
            "\n".join(
                f"{item['key']}={'' if item.get('secret') else (item.get('value') or '')}"
                for item in (config.environment_variables or [])
            )
            + "\n"
        )

        result = {
            "dockerfile": dockerfile,
            "entrypoint": entrypoint,
            "requirements_txt": requirements_txt,
            "runtime_manifest": runtime_manifest,
            "custom_nodes_lock": custom_nodes_lock,
            "models_manifest": models_manifest,
            "env_example": env_example,
        }

        if modal_enabled:
            volume_name = f"{RuntimeBuilderService.sanitize_runtime_name(config.runtime_name)}-models"
            for volume in config.volumes or []:
                if volume.get("name"):
                    volume_name = str(volume["name"])
                    break
            result["modal_app"] = RuntimeBuilderService._modal_app(volume_name, volume_path, RuntimeBuilderService.sanitize_runtime_name(config.runtime_name))
            if external_models:
                result["extra_model_paths"] = RuntimeBuilderService._extra_model_paths_yaml(
                    volume_path
                )

        return result
