import json
import re
from dataclasses import asdict, dataclass

from app.models.runtime_builder_config import RuntimeBuilderConfig


@dataclass
class ValidationIssue:
    level: str
    field: str
    message: str


class RuntimeBuilderService:

    @staticmethod
    def normalize_cuda_version(value: str | None) -> str:
        version = str(value or "").strip()
        if re.fullmatch(r"\d+\.\d+", version):
            return f"{version}.0"
        if re.fullmatch(r"\d+\.\d+\.\d+", version):
            return version
        raise ValueError("La versión CUDA debe usar el formato mayor.menor o mayor.menor.parche, por ejemplo 12.8 o 12.8.0.")
    @staticmethod
    def validate(config: RuntimeBuilderConfig) -> dict:
        issues: list[ValidationIssue] = []
        if not config.comfyui_commit:
            issues.append(ValidationIssue("warning", "comfyui_commit", "Conviene fijar un commit de ComfyUI para builds reproducibles."))
        if ":" not in config.registry_image:
            issues.append(ValidationIssue("warning", "registry_image", "La imagen no contiene un tag explícito; se agregará la versión del runtime."))
        if not re.match(r"^\d+\.\d+\.\d+([-.][A-Za-z0-9.]+)?$", config.runtime_version):
            issues.append(ValidationIssue("error", "runtime_version", "La versión debe seguir un formato semántico, por ejemplo 1.0.0."))
        names: set[str] = set()
        for index, node in enumerate(config.custom_nodes or []):
            name = str(node.get("name", "")).strip().lower()
            if not node.get("enabled", True):
                continue
            if name in names:
                issues.append(ValidationIssue("error", f"custom_nodes.{index}.name", "Existe un custom node duplicado."))
            names.add(name)
            if not str(node.get("repository", "")).startswith(("https://", "git@")):
                issues.append(ValidationIssue("error", f"custom_nodes.{index}.repository", "El repositorio del nodo no es válido."))
            if not node.get("commit"):
                issues.append(ValidationIssue("warning", f"custom_nodes.{index}.commit", "El nodo no tiene commit fijo."))
        enabled_models = [item for item in (config.models or []) if item.get("enabled", True)]
        for index, model in enumerate(enabled_models):
            if model.get("strategy") in {"image", "startup-download"} and not model.get("source_url"):
                issues.append(ValidationIssue("error", f"models.{index}.source_url", "El modelo necesita una URL para esta estrategia."))
            sha = model.get("sha256")
            if sha and not re.fullmatch(r"[a-fA-F0-9]{64}", sha):
                issues.append(ValidationIssue("error", f"models.{index}.sha256", "SHA-256 debe contener 64 caracteres hexadecimales."))
        return {
            "valid": not any(issue.level == "error" for issue in issues),
            "issues": [asdict(issue) for issue in issues],
            "summary": {
                "custom_nodes": len([n for n in (config.custom_nodes or []) if n.get("enabled", True)]),
                "models": len(enabled_models),
                "python_dependencies": len([d for d in (config.python_dependencies or []) if d.get("enabled", True)]),
                "volumes": len(config.volumes or []),
                "reproducible": bool(config.comfyui_commit) and all(bool(n.get("commit")) for n in (config.custom_nodes or []) if n.get("enabled", True)),
            },
        }

    @staticmethod
    def generate(config: RuntimeBuilderConfig) -> dict:
        nodes = [n for n in (config.custom_nodes or []) if n.get("enabled", True)]
        deps = [d for d in (config.python_dependencies or []) if d.get("enabled", True)]
        models = [m for m in (config.models or []) if m.get("enabled", True)]
        node_lines: list[str] = []
        for node in nodes:
            folder = re.sub(r"[^A-Za-z0-9_.-]", "-", node["name"]).strip("-")
            node_lines.append(f"RUN git clone {node['repository']} /opt/ComfyUI/custom_nodes/{folder}")
            if node.get("commit"):
                node_lines.append(f"RUN git -C /opt/ComfyUI/custom_nodes/{folder} checkout {node['commit']}")
            if node.get("install_requirements", True):
                node_lines.append(f"RUN if [ -f /opt/ComfyUI/custom_nodes/{folder}/requirements.txt ]; then pip install --no-cache-dir -r /opt/ComfyUI/custom_nodes/{folder}/requirements.txt; fi")
        pip_packages = [f"{d['package']}{'==' + d['version'] if d.get('version') else ''}" for d in deps]
        model_lines = []
        for model in models:
            if model.get("strategy") == "image":
                model_lines.append(f"RUN mkdir -p $(dirname /opt/ComfyUI/models/{model['target_path']}) && curl -fL '{model['source_url']}' -o /opt/ComfyUI/models/{model['target_path']}")
        commit_line = f"RUN git -C /opt/ComfyUI checkout {config.comfyui_commit}" if config.comfyui_commit else ""
        dockerfile = "\n".join(filter(None, [
            f"FROM nvidia/cuda:{RuntimeBuilderService.normalize_cuda_version(config.cuda_version)}-cudnn-runtime-ubuntu22.04",
            "ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1",
            "RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip python3-venv git curl ffmpeg libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*",
            f"RUN git clone {config.comfyui_repository} /opt/ComfyUI",
            commit_line,
            f"RUN pip install --index-url {config.pytorch_index_url} torch torchvision torchaudio",
            "RUN pip install -r /opt/ComfyUI/requirements.txt",
            *node_lines,
            f"RUN pip install {' '.join(pip_packages)}" if pip_packages else "",
            *model_lines,
            "COPY runpod_worker /opt/tryon/runpod_worker",
            "WORKDIR /opt/tryon/runpod_worker",
            "RUN pip install -r requirements.txt",
            "COPY runtime-builder/entrypoint.sh /opt/tryon/entrypoint.sh",
            "RUN chmod +x /opt/tryon/entrypoint.sh",
            "ENTRYPOINT [\"/opt/tryon/entrypoint.sh\"]",
        ])) + "\n"
        entrypoint = """#!/usr/bin/env bash
set -euo pipefail
python3 /opt/ComfyUI/main.py --listen 127.0.0.1 --port 8188 &
COMFY_PID=$!
for _ in $(seq 1 120); do
  curl -fsS http://127.0.0.1:8188/system_stats >/dev/null && break
  sleep 1
done
python3 /opt/tryon/runpod_worker/handler.py
wait $COMFY_PID
"""
        runtime_manifest = {
            "contract": "tryon.runtime-builder/v1",
            "name": config.name,
            "version": config.runtime_version,
            "platform": config.target_platform,
            "registry_image": config.registry_image,
            "comfyui": {"repository": config.comfyui_repository, "commit": config.comfyui_commit},
            "python": config.python_version,
            "cuda": config.cuda_version,
            "volumes": config.volumes or [],
        }
        custom_nodes_lock = {"nodes": nodes}
        models_manifest = {"models": models}
        env_example = "\n".join(f"{item['key']}={'' if item.get('secret') else (item.get('value') or '')}" for item in (config.environment_variables or [])) + "\n"
        return {
            "dockerfile": dockerfile,
            "entrypoint": entrypoint,
            "runtime_manifest": runtime_manifest,
            "custom_nodes_lock": custom_nodes_lock,
            "models_manifest": models_manifest,
            "env_example": env_example,
        }
