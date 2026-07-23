from __future__ import annotations
import hashlib, json, os, re, shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from app.models.runtime_builder_config import RuntimeBuilderConfig
from app.services.runtime_builder_service import RuntimeBuilderService

class RuntimeContextGeneratorService:
    @staticmethod
    def _safe(value: str) -> str:
        return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-._") or "runtime"

    @staticmethod
    def _sha256(path: Path) -> str:
        digest=hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(8*1024*1024), b""): digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _find_comfyui(path: str) -> Path:
        selected=Path(path).expanduser().resolve()
        candidates=[selected, selected/"ComfyUI", *[parent/"ComfyUI" for parent in list(selected.parents)[:4]]]
        for candidate in candidates:
            if (candidate/"main.py").is_file() and (candidate/"models").is_dir(): return candidate
        raise ValueError("No se encontró una instalación válida de ComfyUI en la ruta indicada.")

    @staticmethod
    def _find_model(comfy: Path, item: dict[str,Any]) -> Path|None:
        root=comfy/"models"; target=str(item.get("target_path") or "").replace("\\","/").lstrip("/"); name=str(item.get("name") or "").strip()
        direct=root/target if target else None
        if direct and direct.is_file(): return direct
        needle=Path(target).name if target else name
        matches=[p for p in root.rglob("*") if p.is_file() and p.name.lower()==needle.lower()] if needle else []
        return matches[0] if len(matches)==1 else None

    @staticmethod
    def _find_node(comfy: Path, item: dict[str,Any]) -> Path|None:
        root=comfy/"custom_nodes"
        if not root.exists(): return None
        name=RuntimeContextGeneratorService._safe(str(item.get("name") or "")).lower()
        repo=str(item.get("repository") or "").rstrip("/").removesuffix(".git").split("/")[-1].lower()
        for folder in root.iterdir():
            if not folder.is_dir() or folder.name.startswith("."): continue
            norm=RuntimeContextGeneratorService._safe(folder.name).lower()
            if norm in {name,repo} or (name and name in norm) or (repo and repo in norm): return folder
        return None

    @staticmethod
    def generate(config: RuntimeBuilderConfig, payload: Any) -> dict[str,Any]:
        comfy=RuntimeContextGeneratorService._find_comfyui(payload.comfyui_path)
        base=Path(payload.output_directory).expanduser().resolve() if payload.output_directory else Path(os.getenv("RUNTIME_EXPORTS_DIR","runtime_exports")).resolve()
        output=base/f"{RuntimeContextGeneratorService._safe(config.name)}-{RuntimeContextGeneratorService._safe(config.runtime_version)}"
        if output.exists():
            if not payload.overwrite: raise ValueError(f"El directorio de salida ya existe: {output}. Activa sobrescribir para reemplazarlo.")
            shutil.rmtree(output)
        for folder in ("models","custom_nodes","workflow","scripts"): (output/folder).mkdir(parents=True,exist_ok=True)
        generated=RuntimeBuilderService.generate(config); warnings=[]; model_manifest=[]; node_manifest=[]; total=0; models_copied=0; nodes_copied=0
        for item in [m for m in (config.models or []) if m.get("enabled",True)]:
            source=RuntimeContextGeneratorService._find_model(comfy,item); record=dict(item)
            if not source:
                warnings.append(f"Modelo no localizado: {item.get('target_path') or item.get('name')}"); record.update({"included":False,"source_path":None}); model_manifest.append(record); continue
            relative=source.relative_to(comfy/"models"); destination=output/"models"/relative; size=source.stat().st_size
            sha=RuntimeContextGeneratorService._sha256(source) if payload.calculate_sha256 else item.get("sha256")
            if payload.copy_models:
                destination.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(source,destination); models_copied+=1; total+=size
            record.update({"included":bool(payload.copy_models),"source_path":str(source),"context_path":f"models/{relative.as_posix()}","size_bytes":size,"sha256":sha}); model_manifest.append(record)
        ignored=shutil.ignore_patterns(".git","__pycache__","*.pyc",".venv","venv","node_modules",".idea",".vscode")
        for item in [n for n in (config.custom_nodes or []) if n.get("enabled",True)]:
            source=RuntimeContextGeneratorService._find_node(comfy,item); record=dict(item)
            if not source:
                warnings.append(f"Custom Node no localizado: {item.get('name')}"); record.update({"included":False,"source_path":None}); node_manifest.append(record); continue
            destination=output/"custom_nodes"/source.name
            if payload.copy_custom_nodes:
                shutil.copytree(source,destination,ignore=ignored); nodes_copied+=1; total+=sum(p.stat().st_size for p in destination.rglob("*") if p.is_file())
            record.update({"included":bool(payload.copy_custom_nodes),"source_path":str(source),"context_path":f"custom_nodes/{source.name}"}); node_manifest.append(record)
        deps=[d for d in (config.python_dependencies or []) if d.get("enabled",True)]
        requirements="\n".join(f"{d['package']}{'=='+d['version'] if d.get('version') else ''}" for d in deps)+( "\n" if deps else "")
        manifest={"contract":"tryon.runtime-context/v2","generated_at":datetime.now(timezone.utc).isoformat(),"runtime":generated["runtime_manifest"],"source_comfyui":str(comfy),"copy_mode":{"models":payload.copy_models,"custom_nodes":payload.copy_custom_nodes},"models":model_manifest,"custom_nodes":node_manifest,"summary":{"models_copied":models_copied,"custom_nodes_copied":nodes_copied,"bytes_copied":total,"warnings":len(warnings)}}
        health='import json, urllib.request\nwith urllib.request.urlopen("http://127.0.0.1:8188/system_stats", timeout=10) as r:\n    print(json.dumps({"ok": r.status == 200}))\n'
        files={"Dockerfile":RuntimeContextGeneratorService._dockerfile(config,payload.copy_models,payload.copy_custom_nodes),"requirements.txt":requirements,"runtime.json":json.dumps(generated["runtime_manifest"],indent=2,ensure_ascii=False),"manifest.json":json.dumps(manifest,indent=2,ensure_ascii=False),"models-manifest.json":json.dumps({"models":model_manifest},indent=2,ensure_ascii=False),"custom-nodes.lock.json":json.dumps({"nodes":node_manifest},indent=2,ensure_ascii=False),".env.example":generated["env_example"],"scripts/startup.sh":generated["entrypoint"],"scripts/healthcheck.py":health,".dockerignore":"**/.git\n**/__pycache__\n**/*.pyc\n.venv\nnode_modules\n"}
        for relative,content in files.items():
            destination=output/relative; destination.parent.mkdir(parents=True,exist_ok=True); destination.write_text(content,encoding="utf-8",newline="\n")
        archive=shutil.make_archive(str(output),"zip",root_dir=output)
        return {"success":True,"output_directory":str(output),"archive_path":archive,"models_copied":models_copied,"custom_nodes_copied":nodes_copied,"bytes_copied":total,"files_generated":sorted(files),"warnings":warnings,"manifest":manifest}

    @staticmethod
    def _dockerfile(config: RuntimeBuilderConfig, models: bool, nodes: bool) -> str:
        lines=[f"FROM nvidia/cuda:{config.cuda_version}-cudnn-runtime-ubuntu22.04","ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1","RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip python3-venv git curl ffmpeg libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*",f"RUN git clone {config.comfyui_repository} /opt/ComfyUI"]
        if config.comfyui_commit: lines.append(f"RUN git -C /opt/ComfyUI checkout {config.comfyui_commit}")
        lines += [f"RUN pip3 install --index-url {config.pytorch_index_url} torch torchvision torchaudio","RUN pip3 install -r /opt/ComfyUI/requirements.txt","COPY requirements.txt /tmp/runtime-requirements.txt","RUN if [ -s /tmp/runtime-requirements.txt ]; then pip3 install -r /tmp/runtime-requirements.txt; fi"]
        if nodes: lines += ["COPY custom_nodes/ /opt/ComfyUI/custom_nodes/","RUN find /opt/ComfyUI/custom_nodes -name requirements.txt -print0 | xargs -0 -r -n1 pip3 install -r"]
        if models: lines.append("COPY models/ /opt/ComfyUI/models/")
        lines += ["COPY scripts/ /opt/tryon/scripts/","RUN chmod +x /opt/tryon/scripts/startup.sh","WORKDIR /opt/ComfyUI","HEALTHCHECK --interval=30s --timeout=10s --start-period=120s CMD python3 /opt/tryon/scripts/healthcheck.py || exit 1","ENTRYPOINT [\"/opt/tryon/scripts/startup.sh\"]"]
        return "\n".join(lines)+"\n"
