from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.models.runtime_builder_config import RuntimeBuilderConfig
from app.services.runtime_builder_service import RuntimeBuilderService


ProgressCallback = Callable[[str, int, str], None]


class RuntimeContextGeneratorService:
    @staticmethod
    def _safe(value: str) -> str:
        return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-._") or "runtime"

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _find_comfyui(path: str) -> Path:
        selected = Path(path).expanduser().resolve()
        candidates = [
            selected,
            selected / "ComfyUI",
            *[parent / "ComfyUI" for parent in list(selected.parents)[:4]],
        ]
        for candidate in candidates:
            if (candidate / "main.py").is_file() and (candidate / "models").is_dir():
                return candidate
        raise ValueError("No se encontró una instalación válida de ComfyUI en la ruta indicada.")

    @staticmethod
    def _find_model(comfy: Path, item: dict[str, Any]) -> Path | None:
        root = comfy / "models"
        target = str(item.get("target_path") or "").replace("\\", "/").lstrip("/")
        name = str(item.get("name") or "").strip()
        direct = root / target if target else None
        if direct and direct.is_file():
            return direct
        needle = Path(target).name if target else name
        matches = [
            path for path in root.rglob("*")
            if path.is_file() and path.name.lower() == needle.lower()
        ] if needle else []
        return matches[0] if len(matches) == 1 else None

    @staticmethod
    def _normalize_node_name(value: str | None) -> str:
        """Normaliza nombres de repositorios/carpetas sin perder identidad.

        Ignora mayúsculas, espacios, guiones y guiones bajos para reconocer
        forks o carpetas renombradas, pero mantiene la copia exacta del nodo
        local encontrado.
        """
        return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())

    @staticmethod
    def _find_node(comfy: Path, item: dict[str, Any]) -> Path | None:
        root = comfy / "custom_nodes"
        if not root.exists():
            return None

        configured_name = str(item.get("name") or "").strip()
        repository_name = (
            str(item.get("repository") or "")
            .rstrip("/")
            .removesuffix(".git")
            .split("/")[-1]
        )

        canonical_keys = {
            RuntimeContextGeneratorService._normalize_node_name(configured_name),
            RuntimeContextGeneratorService._normalize_node_name(repository_name),
        }
        canonical_keys.discard("")

        aliases: set[str] = set()
        for canonical, values in RuntimeBuilderService.CUSTOM_NODE_ALIASES.items():
            canonical_normalized = RuntimeContextGeneratorService._normalize_node_name(canonical)
            if canonical_normalized in canonical_keys:
                aliases.update(values)

        accepted = canonical_keys | {
            RuntimeContextGeneratorService._normalize_node_name(alias)
            for alias in aliases
        }
        accepted.discard("")

        folders = [
            folder for folder in root.iterdir()
            if folder.is_dir() and not folder.name.startswith(".")
        ]

        # Primero exige coincidencia exacta normalizada. Esto evita que nombres
        # genéricos como "logic" seleccionen accidentalmente otro paquete.
        for folder in folders:
            if RuntimeContextGeneratorService._normalize_node_name(folder.name) in accepted:
                return folder

        # Compatibilidad conservadora con el comportamiento anterior para nodos
        # sin alias explícito y nombres de repositorio con sufijos adicionales.
        for folder in folders:
            normalized = RuntimeContextGeneratorService._normalize_node_name(folder.name)
            if any(len(key) >= 8 and (key in normalized or normalized in key) for key in canonical_keys):
                return folder
        return None

    @staticmethod
    def _normalize_copied_requirements(root: Path) -> list[str]:
        """Normaliza requisitos de ejecución y elimina herramientas solo de desarrollo."""
        changed: list[str] = []
        mediapipe_pattern = re.compile(r"(?i)^\s*mediapipe\s*==\s*0\.10\.0\s*$")
        av_pattern = re.compile(r"(?i)^\s*av\s*==\s*(?:8|9|10|11)(?:\.\d+){0,2}\s*$")
        for requirement_file in root.rglob("requirements.txt"):
            try:
                original = requirement_file.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                original = requirement_file.read_text(encoding="utf-8", errors="ignore")

            output_lines: list[str] = []
            for line in original.splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or stripped.startswith(("-r ", "--requirement ", "-c ", "--constraint ")):
                    output_lines.append(line)
                    continue
                normalized_line = mediapipe_pattern.sub("mediapipe==0.10.21", line)
                normalized_line = av_pattern.sub("av==12.3.0", normalized_line)
                if not RuntimeBuilderService.is_runtime_dependency(normalized_line):
                    continue
                output_lines.append(normalized_line)

            normalized = "\n".join(output_lines) + ("\n" if original.endswith(("\n", "\r")) else "")
            if normalized != original:
                requirement_file.write_text(normalized, encoding="utf-8")
                changed.append(str(requirement_file))
        return changed

    @staticmethod
    def generate(
        config: RuntimeBuilderConfig,
        payload: Any,
        progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        notify = progress or (lambda _phase, _percent, _message: None)
        notify("preparing", 2, "Validando instalación local de ComfyUI…")
        comfy = RuntimeContextGeneratorService._find_comfyui(payload.comfyui_path)
        base = (
            Path(payload.output_directory).expanduser().resolve()
            if payload.output_directory
            else (
                Path(config.export_root_directory).expanduser().resolve()
                if config.export_root_directory
                else Path(os.getenv("RUNTIME_EXPORTS_DIR", "runtime_exports")).resolve()
            )
        )
        output = base / (
            f"{RuntimeContextGeneratorService._safe(config.runtime_name or config.name)}-"
            f"{RuntimeContextGeneratorService._safe(config.runtime_version)}"
        )
        if output.exists():
            if not payload.overwrite:
                raise ValueError(
                    f"El directorio de salida ya existe: {output}. "
                    "Activa sobrescribir para reemplazarlo."
                )
            shutil.rmtree(output)

        for folder in ("models", "custom_nodes", "workflow", "scripts"):
            (output / folder).mkdir(parents=True, exist_ok=True)

        generated = RuntimeBuilderService.generate(config)

        # La decisión real de copiar modelos pertenece a la exportación. Si el
        # usuario desmarca "Copiar modelos" y existe un Volume configurado, se
        # fuerza el contexto Modal aunque los modelos detectados conservaran una
        # estrategia anterior. Así siempre se generan modal_app.py y
        # extra_model_paths.yaml para el directorio exportado.
        external_volume_models = not payload.copy_models and bool(config.volumes)
        if external_volume_models:
            volume_path = RuntimeBuilderService._modal_volume_path(config)
            generated["extra_model_paths"] = RuntimeBuilderService._extra_model_paths_yaml(volume_path)
            generated["runtime_manifest"]["model_storage"] = "external-volume"
            if RuntimeBuilderService._is_modal(config):
                volume_name = next(
                    (str(volume.get("name")) for volume in (config.volumes or []) if volume.get("name")),
                    f"{RuntimeBuilderService.sanitize_runtime_name(config.runtime_name)}-models",
                )
                generated["modal_app"] = RuntimeBuilderService._modal_app(volume_name, volume_path, RuntimeBuilderService.sanitize_runtime_name(config.runtime_name))
                generated["runtime_manifest"]["provider"] = "modal"

        warnings: list[str] = []
        model_manifest: list[dict[str, Any]] = []
        node_manifest: list[dict[str, Any]] = []
        total = 0
        models_copied = 0
        nodes_copied = 0

        enabled_models = [m for m in (config.models or []) if m.get("enabled", True)]
        sam3_tree_copied = False
        notify("models", 8, "Revisando modelos requeridos por el workflow…")
        for index, item in enumerate(enabled_models):
            source = RuntimeContextGeneratorService._find_model(comfy, item)
            record = dict(item)
            if not source:
                warnings.append(f"Modelo no localizado: {item.get('target_path') or item.get('name')}")
                record.update({"included": False, "source_path": None})
                model_manifest.append(record)
                continue
            relative = source.relative_to(comfy / "models")
            destination = output / "models" / relative
            size = source.stat().st_size
            sha = RuntimeContextGeneratorService._sha256(source) if payload.calculate_sha256 else item.get("sha256")
            if payload.copy_models:
                # TBG-SAM3 necesita el repositorio local completo (config, tokenizer,
                # processor y pesos auxiliares), no solamente sam3.pt. Se conserva
                # el comportamiento selectivo para todas las demás categorías.
                if relative.parts and relative.parts[0].lower() == "sam3":
                    if not sam3_tree_copied:
                        sam3_source = comfy / "models" / relative.parts[0]
                        sam3_destination = output / "models" / relative.parts[0]
                        shutil.copytree(sam3_source, sam3_destination, dirs_exist_ok=True)
                        copied_files = [path for path in sam3_source.rglob("*") if path.is_file()]
                        models_copied += len(copied_files)
                        total += sum(path.stat().st_size for path in copied_files)
                        sam3_tree_copied = True
                else:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
                    models_copied += 1
                    total += size
            record.update({
                "included": bool(payload.copy_models),
                "source_path": str(source),
                "context_path": f"models/{relative.as_posix()}",
                "size_bytes": size,
                "sha256": sha,
            })
            model_manifest.append(record)
            notify("models", 8 + int(37 * (index + 1) / max(1, len(enabled_models))), "Procesando modelos…")

        ignored = shutil.ignore_patterns(
            ".git", "__pycache__", "*.pyc", ".venv", "venv", "node_modules", ".idea", ".vscode"
        )
        enabled_nodes = [n for n in RuntimeBuilderService.merge_required_custom_nodes(config.custom_nodes) if n.get("enabled", True)]
        copied_node_sources: dict[str, str] = {}
        notify("custom_nodes", 47, "Copiando Custom Nodes requeridos…")
        for index, item in enumerate(enabled_nodes):
            source = RuntimeContextGeneratorService._find_node(comfy, item)
            record = dict(item)
            if not source:
                warnings.append(f"Custom Node no localizado: {item.get('name')}")
                record.update({"included": False, "source_path": None})
                node_manifest.append(record)
                continue

            source_key = os.path.normcase(str(source.resolve()))
            context_path = f"custom_nodes/{source.name}"
            destination = output / context_path
            duplicate_of = copied_node_sources.get(source_key)

            if payload.copy_custom_nodes and duplicate_of is None:
                shutil.copytree(
                    source,
                    destination,
                    ignore=ignored,
                    dirs_exist_ok=True,
                )
                copied_node_sources[source_key] = context_path
                normalized_files = RuntimeContextGeneratorService._normalize_copied_requirements(destination)
                for normalized_file in normalized_files:
                    warnings.append(
                        "Requirements de Custom Node normalizados para producción "
                        f"({normalized_file})."
                    )
                nodes_copied += 1
                total += sum(path.stat().st_size for path in destination.rglob("*") if path.is_file())
            elif payload.copy_custom_nodes and duplicate_of is not None:
                warnings.append(
                    f"Custom Node duplicado omitido: {item.get('name') or source.name} "
                    f"(usa el mismo directorio que {duplicate_of})."
                )

            record.update({
                "included": bool(payload.copy_custom_nodes),
                "source_path": str(source),
                "context_path": duplicate_of or context_path,
                "duplicate": duplicate_of is not None,
            })
            node_manifest.append(record)
            notify(
                "custom_nodes",
                47 + int(28 * (index + 1) / max(1, len(enabled_nodes))),
                "Procesando Custom Nodes…",
            )

        dependencies = [d for d in (config.python_dependencies or []) if d.get("enabled", True)]
        requirements_lines = RuntimeBuilderService.render_requirements(dependencies)
        requirements = "\n".join(requirements_lines) + ("\n" if requirements_lines else "")

        manifest = {
            "contract": "runtime-context/v3",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "runtime": generated["runtime_manifest"],
            "project_key": config.project_key,
            "module_type": config.module_type,
            "container_workdir": config.container_workdir,
            "source_comfyui": str(comfy),
            "copy_mode": {
                "models": payload.copy_models,
                "custom_nodes": payload.copy_custom_nodes,
            },
            "models": model_manifest,
            "custom_nodes": node_manifest,
            "summary": {
                "models_copied": models_copied,
                "custom_nodes_copied": nodes_copied,
                "bytes_copied": total,
                "warnings": len(warnings),
                "archive_created": False,
            },
        }

        health = (
            'import json, urllib.request\n'
            'with urllib.request.urlopen("http://127.0.0.1:8188/system_stats", timeout=10) as r:\n'
            '    print(json.dumps({"ok": r.status == 200}))\n'
        )
        workdir = (config.container_workdir or "/app").rstrip("/")
        performance_probe = r'''import importlib.util
import json
import os
import subprocess


def available(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


report = {
    "provider": os.getenv("RUNTIME_PROVIDER", "docker"),
    "comfyui_extra_args": os.getenv("COMFYUI_EXTRA_ARGS", ""),
    "flash_attn": available("flash_attn"),
    "xformers": available("xformers"),
    "triton": available("triton"),
}
try:
    import torch
    report.update({
        "pytorch": torch.__version__,
        "cuda_runtime": torch.version.cuda,
        "cuda_available": torch.cuda.is_available(),
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "capability": list(torch.cuda.get_device_capability(0)) if torch.cuda.is_available() else None,
        "vram_bytes": torch.cuda.get_device_properties(0).total_memory if torch.cuda.is_available() else 0,
    })
except Exception as exc:
    report["torch_error"] = str(exc)
try:
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
        capture_output=True, text=True, timeout=10, check=False,
    )
    report["nvidia_driver"] = result.stdout.strip() or None
except Exception:
    report["nvidia_driver"] = None
print("[runtime-performance] " + json.dumps(report, ensure_ascii=False, sort_keys=True))
'''
        startup = f'''#!/usr/bin/env bash
set -euo pipefail

MODELS_ROOT="${{MODELS_ROOT:-/models}}"
COMFY_MODELS="{workdir}/ComfyUI/models"
mkdir -p "$COMFY_MODELS"
if [ -d "$MODELS_ROOT/sam3" ]; then
  rm -rf "$COMFY_MODELS/sam3"
  ln -s "$MODELS_ROOT/sam3" "$COMFY_MODELS/sam3"
  echo "[runtime] SAM3 enlazado: $COMFY_MODELS/sam3 -> $MODELS_ROOT/sam3"
fi

python {workdir}/runtime/scripts/performance_probe.py || true
read -r -a EXTRA_ARGS <<< "${{COMFYUI_EXTRA_ARGS:-}}"
python {workdir}/ComfyUI/main.py --listen 0.0.0.0 --port 8188 "${{EXTRA_ARGS[@]}}" &
COMFY_PID=$!
for _ in $(seq 1 180); do
  curl -fsS http://127.0.0.1:8188/system_stats >/dev/null && break
  sleep 1
done
if [ -f {workdir}/tryon/runpod_worker/handler.py ]; then
  python {workdir}/tryon/runpod_worker/handler.py
else
  wait $COMFY_PID
fi
'''

        files: dict[str, str] = {
            "Dockerfile": RuntimeContextGeneratorService._dockerfile(
                config,
                payload.copy_models,
                payload.copy_custom_nodes,
            ),
            "requirements.txt": requirements,
            "runtime.json": json.dumps(generated["runtime_manifest"], indent=2, ensure_ascii=False),
            "manifest.json": json.dumps(manifest, indent=2, ensure_ascii=False),
            "models-manifest.json": json.dumps({"models": model_manifest}, indent=2, ensure_ascii=False),
            "custom-nodes.lock.json": json.dumps({"nodes": node_manifest}, indent=2, ensure_ascii=False),
            ".env.example": generated["env_example"],
            "scripts/startup.sh": startup,
            "scripts/healthcheck.py": health,
            "scripts/performance_probe.py": performance_probe,
            ".dockerignore": "**/.git\n**/__pycache__\n**/*.pyc\n.venv\nnode_modules\n",
        }
        if generated.get("modal_app"):
            files["modal_app.py"] = generated["modal_app"]
        if generated.get("extra_model_paths"):
            files["extra_model_paths.yaml"] = generated["extra_model_paths"]

        notify("writing", 80, "Escribiendo el contexto de build…")
        for relative, content in files.items():
            destination = output / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content, encoding="utf-8", newline="\n")

        notify("completed", 99, "Contexto de runtime generado sin crear ZIP de respaldo.")
        return {
            "success": True,
            "export_root_directory": str(base),
            "output_directory": str(output),
            "archive_path": "",
            "models_copied": models_copied,
            "custom_nodes_copied": nodes_copied,
            "bytes_copied": total,
            "files_generated": sorted(files),
            "warnings": warnings,
            "manifest": manifest,
        }

    @staticmethod
    def _dockerfile(config: RuntimeBuilderConfig, models: bool, nodes: bool) -> str:
        workdir = (config.container_workdir or "/app").rstrip("/")
        comfy_target = f"{workdir}/ComfyUI"
        modal_enabled = RuntimeBuilderService._is_modal(config)
        external_models = not models
        lines = [
            f"FROM nvidia/cuda:{RuntimeBuilderService.normalize_cuda_version(config.cuda_version)}-cudnn-runtime-ubuntu22.04",
            'ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PATH="/opt/conda/bin:$PATH" TORCH_CUDA_ARCH_LIST="7.5;8.0;8.6;8.9;9.0;10.0;12.0"',
            "RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates git curl bzip2 ffmpeg libgl1 libopengl0 libglib2.0-0 build-essential pkg-config libgeos-dev libgdal-dev libcairo2-dev libjpeg-dev libpng-dev libtiff-dev libavcodec-dev libavdevice-dev libavfilter-dev libavformat-dev libavutil-dev libswresample-dev libswscale-dev && rm -rf /var/lib/apt/lists/*",
            "RUN geos-config --version && ldconfig -p | grep -F libgeos_c.so",
            "RUN curl -fL https://github.com/conda-forge/miniforge/releases/download/26.3.2-3/Miniforge3-26.3.2-3-Linux-x86_64.sh -o /tmp/miniforge.sh && echo '848194851a98903134187fbb4ab50efe87b003e0c0f808f97644b7524a62bf2c  /tmp/miniforge.sh' | sha256sum -c - && bash /tmp/miniforge.sh -b -p /opt/conda && rm /tmp/miniforge.sh && conda install -y python=3.11 pip && conda clean -afy",
            "RUN python --version && python -m pip install --upgrade 'pip>=25,<26' setuptools wheel",
            f"RUN git clone {config.comfyui_repository} {comfy_target}",
        ]
        if config.comfyui_commit:
            lines.append(f"RUN git -C {comfy_target} checkout {config.comfyui_commit}")
        lines += [
            f"RUN python -m pip install --index-url {config.pytorch_index_url} torch torchvision torchaudio",
            f"RUN printf '%s\\n' 'transformers>=4.50.3,<5' > /tmp/runtime-constraints.txt && sed -Ei 's/^transformers.*$/transformers>=4.50.3,<5/I; /^(torch|torchvision|torchaudio|xformers|triton|onnxruntime-gpu|flash-attn)([<>=!~ ;]|$)/Id' {comfy_target}/requirements.txt && python -m pip install --constraint /tmp/runtime-constraints.txt -r {comfy_target}/requirements.txt",
            "COPY requirements.txt /tmp/runtime-requirements.txt",
            "RUN if [ -s /tmp/runtime-requirements.txt ]; then python -m pip install --constraint /tmp/runtime-constraints.txt -r /tmp/runtime-requirements.txt; fi",
        ]
        if nodes:
            lines += [
                f"COPY custom_nodes/ {comfy_target}/custom_nodes/",
                f"RUN find {comfy_target}/custom_nodes -type f -name requirements.txt -print | sort | while IFS= read -r req; do echo '[runtime] Installing' \"$req\"; sed -Ei \"/^(torch|torchvision|torchaudio|xformers|triton|onnxruntime-gpu|flash-attn)([<>=!~ ;]|\\$)/Id\" \"$req\"; python -m pip install --constraint /tmp/runtime-constraints.txt -r \"$req\" || exit 1; done",
                'RUN set -eu; check_output="$(python -m pip check 2>&1)" && { printf \'%s\\n\' "$check_output"; exit 0; }; check_status=$?; printf \'%s\\n\' "$check_output"; unexpected="$(printf \'%s\\n\' "$check_output" | sed -E \'/^decord 0\\.6\\.0 is not supported on this platform$/d; /^[[:space:]]*$/d\')"; if [ -n "$unexpected" ]; then echo \'[runtime] pip check encontró errores no permitidos.\' >&2; exit "$check_status"; fi; echo \'[runtime] Advertencia conocida ignorada: decord 0.6.0 no declara soporte para esta plataforma.\'',
                "RUN python -c 'import sys, torch, transformers; assert sys.version_info[:2] == (3, 11); assert torch.version.cuda and torch.version.cuda.startswith(\"12.8\"); assert int(transformers.__version__.split(\".\")[0]) < 5; print(sys.version); print(torch.__version__, torch.version.cuda); print(transformers.__version__)'",
            ]
        if models:
            lines.append(f"COPY models/ {comfy_target}/models/")
        elif external_models:
            lines.append(f"COPY extra_model_paths.yaml {comfy_target}/extra_model_paths.yaml")
        lines += [
            f"COPY scripts/ {workdir}/runtime/scripts/",
            f"RUN chmod +x {workdir}/runtime/scripts/startup.sh",
            f"WORKDIR {comfy_target}",
            f"HEALTHCHECK --interval=30s --timeout=10s --start-period=120s CMD python {workdir}/runtime/scripts/healthcheck.py || exit 1",
            f'ENTRYPOINT ["{workdir}/runtime/scripts/startup.sh"]',
        ]
        return "\n".join(lines) + "\n"
