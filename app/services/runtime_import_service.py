from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from app.models.runtime_builder_config import RuntimeBuilderConfig

MODEL_EXTENSIONS = {'.safetensors', '.ckpt', '.pt', '.pth', '.bin', '.onnx', '.gguf'}
MODEL_TYPE_BY_FOLDER = {
    'checkpoints': 'checkpoint', 'vae': 'vae', 'loras': 'lora', 'lora': 'lora',
    'controlnet': 'controlnet', 'clip': 'clip', 'clip_vision': 'clip',
    'upscale_models': 'upscaler', 'upscalers': 'upscaler', 'embeddings': 'embedding',
    'ultralytics': 'detector', 'sams': 'sam', 'sam': 'sam', 'ipadapter': 'ipadapter',
}
IGNORED_DIRS = {'models', 'output', 'input', '.git', 'node_modules', '__pycache__', '.cache'}


class RuntimeImportService:
    @staticmethod
    def _run(command: list[str], cwd: Path | None = None, timeout: int = 20) -> str | None:
        try:
            result = subprocess.run(command, cwd=str(cwd) if cwd else None, capture_output=True, text=True,
                                    timeout=timeout, check=False, creationflags=0)
            if result.returncode == 0:
                return result.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return None
        return None

    @staticmethod
    def _find_comfy_root(selected: Path) -> tuple[Path, str]:
        selected = selected.expanduser().resolve()
        if not selected.exists() or not selected.is_dir():
            raise ValueError('La carpeta seleccionada no existe o no es accesible por el Backend.')
        candidates = [selected, selected / 'ComfyUI', selected / 'app', selected / 'app' / 'ComfyUI']
        for path in candidates:
            if (path / 'main.py').exists() and (path / 'custom_nodes').is_dir():
                return path, RuntimeImportService._detect_source(selected, path)
        base_depth = len(selected.parts)
        for current, directories, files in os.walk(selected):
            current_path = Path(current)
            depth = len(current_path.parts) - base_depth
            directories[:] = [d for d in directories if d.lower() not in IGNORED_DIRS and depth < 9]
            if 'main.py' in files and (current_path / 'custom_nodes').is_dir():
                return current_path.resolve(), RuntimeImportService._detect_source(selected, current_path)
        raise ValueError('No se encontró una instalación válida de ComfyUI dentro de la carpeta indicada.')

    @staticmethod
    def _detect_source(selected: Path, comfy: Path) -> str:
        text = f'{selected} {comfy}'.lower()
        if 'pinokio' in text or any((p / 'pinokio.js').exists() for p in [selected, *selected.parents[:2]]): return 'pinokio'
        if 'stabilitymatrix' in text or 'stability matrix' in text: return 'stability-matrix'
        if any((p / 'python_embeded').exists() for p in [selected, comfy.parent, comfy.parent.parent]): return 'portable'
        if (comfy / '.git').exists(): return 'git'
        return 'custom'

    @staticmethod
    def _git_info(path: Path) -> tuple[str | None, str | None]:
        if not (path / '.git').exists(): return None, None
        return (RuntimeImportService._run(['git', 'remote', 'get-url', 'origin'], path),
                RuntimeImportService._run(['git', 'rev-parse', 'HEAD'], path))

    @staticmethod
    def _python_candidates(comfy: Path, selected: Path | None = None) -> list[Path]:
        roots = [comfy, comfy.parent, comfy.parent.parent]
        if selected: roots.extend([selected, selected.parent])
        candidates: list[Path] = []
        relative = [
            'venv/Scripts/python.exe', '.venv/Scripts/python.exe', 'env/Scripts/python.exe',
            'python_embeded/python.exe', 'python/python.exe', 'venv/bin/python', '.venv/bin/python',
            'env/bin/python', 'bin/python',
        ]
        for root in roots:
            for rel in relative: candidates.append(root / rel)
        # Pinokio can place the venv beside app/ComfyUI with arbitrary depth.
        for root in roots[:3]:
            if not root.exists(): continue
            base_depth = len(root.parts)
            for current, dirs, files in os.walk(root):
                current_path = Path(current)
                depth = len(current_path.parts) - base_depth
                dirs[:] = [d for d in dirs if d.lower() not in IGNORED_DIRS and depth < 5]
                if 'python.exe' in files and current_path.name.lower() in {'scripts', 'python_embeded', 'python'}:
                    candidates.append(current_path / 'python.exe')
                if 'python' in files and current_path.name.lower() in {'bin', 'venv', '.venv', 'env'}:
                    candidates.append(current_path / 'python')
        unique: list[Path] = []
        seen: set[str] = set()
        for p in candidates:
            key = str(p).lower()
            if key not in seen and p.exists() and p.is_file():
                seen.add(key); unique.append(p)
        return unique

    @staticmethod
    def _probe_python(comfy: Path, selected: Path | None = None) -> dict[str, Any]:
        script = (
            "import json,sys; d={'python':sys.version.split()[0],'executable':sys.executable};"
            "\ntry:\n import torch; d.update(torch=torch.__version__,cuda=torch.version.cuda,"
            "gpu=(torch.cuda.get_device_name(0) if torch.cuda.is_available() else None))"
            "\nexcept Exception as e: d['torch_error']=str(e)"
            "\nprint(json.dumps(d))"
        )
        attempts: list[str] = []
        for python in RuntimeImportService._python_candidates(comfy, selected):
            attempts.append(str(python))
            output = RuntimeImportService._run([str(python), '-c', script], comfy, 40)
            if not output: continue
            try:
                data = json.loads(output.splitlines()[-1])
                data['candidate_attempts'] = attempts
                return data
            except json.JSONDecodeError:
                continue
        return {'python': None, 'torch': None, 'cuda': None, 'gpu': None, 'executable': None,
                'candidate_attempts': attempts}

    @staticmethod
    def _read_node_classes(folder: Path) -> set[str]:
        classes: set[str] = set()
        for file in folder.rglob('*.py'):
            if any(part in {'venv', '.venv', '__pycache__'} for part in file.parts): continue
            try:
                text = file.read_text(encoding='utf-8', errors='ignore')
            except OSError:
                continue
            # Fast and safe static extraction of keys from NODE_CLASS_MAPPINGS dictionaries.
            for match in re.finditer(r'NODE_CLASS_MAPPINGS\s*=\s*\{(.*?)\}', text, re.S):
                classes.update(re.findall(r"['\"]([^'\"]+)['\"]\s*:", match.group(1)))
            for match in re.finditer(r'NODE_CLASS_MAPPINGS\s*\.\s*update\s*\(\s*\{(.*?)\}\s*\)', text, re.S):
                classes.update(re.findall(r"['\"]([^'\"]+)['\"]\s*:", match.group(1)))
        return classes

    @staticmethod
    def _infer_repo(folder: Path) -> str | None:
        repo, _ = RuntimeImportService._git_info(folder)
        if repo: return repo
        for name in ('README.md', 'readme.md', 'pyproject.toml', 'package.json'):
            file = folder / name
            if not file.exists(): continue
            text = file.read_text(encoding='utf-8', errors='ignore')
            match = re.search(r'https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?', text)
            if match: return match.group(0).rstrip(').,]')
        return None

    @staticmethod
    def _workflow_nodes(workflow: dict[str, Any]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        if isinstance(workflow.get('nodes'), list):
            for node in workflow['nodes']:
                if not isinstance(node, dict): continue
                cls = node.get('type') or node.get('class_type')
                result.append({'id': str(node.get('id', '')), 'class_type': str(cls or ''),
                               'inputs': node.get('inputs') or {}, 'widgets_values': node.get('widgets_values') or []})
        else:
            for node_id, node in workflow.items():
                if not isinstance(node, dict) or 'class_type' not in node: continue
                result.append({'id': str(node_id), 'class_type': str(node.get('class_type') or ''),
                               'inputs': node.get('inputs') or {}, 'widgets_values': []})
        return result

    @staticmethod
    def _string_values(value: Any) -> list[str]:
        values: list[str] = []
        if isinstance(value, str): values.append(value)
        elif isinstance(value, dict):
            for child in value.values(): values.extend(RuntimeImportService._string_values(child))
        elif isinstance(value, list):
            # Links are [node_id, output_index], not model references.
            if len(value) == 2 and all(isinstance(v, int) for v in value): return []
            for child in value: values.extend(RuntimeImportService._string_values(child))
        return values

    @staticmethod
    def _looks_like_model(value: str) -> bool:
        low = value.lower().replace('\\', '/')
        return any(low.endswith(ext) for ext in MODEL_EXTENSIONS) or any(token in low for token in (
            '/checkpoints/', '/loras/', '/vae/', '/controlnet/', '/clip/', '/upscale_models/',
            '/ultralytics/', '/sams/', '/ipadapter/'
        ))

    @staticmethod
    def _model_index(comfy: Path) -> tuple[dict[str, list[Path]], int]:
        index: dict[str, list[Path]] = {}
        count = 0
        root = comfy / 'models'
        if not root.exists(): return index, count
        for file in root.rglob('*'):
            if not file.is_file() or file.suffix.lower() not in MODEL_EXTENSIONS: continue
            count += 1
            keys = {file.name.lower(), file.relative_to(root).as_posix().lower()}
            for key in keys: index.setdefault(key, []).append(file)
        return index, count

    @staticmethod
    def _requirements_for_node(folder: Path) -> list[dict[str, Any]]:
        deps: list[dict[str, Any]] = []
        req = folder / 'requirements.txt'
        if req.exists():
            for raw in req.read_text(encoding='utf-8', errors='ignore').splitlines():
                line = raw.strip()
                if not line or line.startswith(('#', '-', 'git+')): continue
                match = re.match(r'^([A-Za-z0-9_.-]+)\s*(?:==|~=|>=|<=|>|<)?\s*(.*)$', line)
                if match:
                    deps.append({'package': match.group(1), 'version': match.group(2) or None, 'enabled': True,
                                 'source': folder.name})
        return deps

    @staticmethod
    def resolve_workflow(path: str, workflow: dict[str, Any]) -> dict[str, Any]:
        selected = Path(path).expanduser().resolve()
        comfy, source = RuntimeImportService._find_comfy_root(selected)
        repo, commit = RuntimeImportService._git_info(comfy)
        python = RuntimeImportService._probe_python(comfy, selected)
        workflow_nodes = RuntimeImportService._workflow_nodes(workflow)
        class_types = sorted({n['class_type'] for n in workflow_nodes if n['class_type']})

        node_catalog: list[dict[str, Any]] = []
        class_to_folder: dict[str, Path] = {}
        custom_root = comfy / 'custom_nodes'
        for folder in sorted(custom_root.iterdir() if custom_root.exists() else []):
            if not folder.is_dir() or folder.name.startswith(('.', '__')): continue
            classes = RuntimeImportService._read_node_classes(folder)
            for cls in classes: class_to_folder.setdefault(cls, folder)
            node_catalog.append({'folder': folder, 'classes': classes})

        required_folders: dict[str, Path] = {}
        unresolved_classes: list[str] = []
        builtin_hint = {'CheckpointLoaderSimple','CLIPTextEncode','KSampler','VAEDecode','VAEEncode','SaveImage','PreviewImage','LoadImage','EmptyLatentImage'}
        for cls in class_types:
            folder = class_to_folder.get(cls)
            if folder: required_folders[folder.name] = folder
            elif cls not in builtin_hint: unresolved_classes.append(cls)

        required_nodes: list[dict[str, Any]] = []
        dependencies_by_name: dict[str, dict[str, Any]] = {}
        node_warnings: list[str] = []
        for name, folder in sorted(required_folders.items()):
            node_repo, node_commit = RuntimeImportService._git_info(folder)
            inferred = node_repo or RuntimeImportService._infer_repo(folder)
            confidence = 'exact-git' if node_repo else ('inferred-readme' if inferred else 'local-only')
            if not inferred: node_warnings.append(f'{name}: usado por el workflow, pero no se pudo determinar su repositorio.')
            required_nodes.append({'name': name, 'repository': inferred or '', 'commit': node_commit,
                                   'enabled': True, 'install_requirements': (folder/'requirements.txt').exists() or (folder/'pyproject.toml').exists(),
                                   'source_path': str(folder), 'confidence': confidence,
                                   'matched_classes': sorted(required_folders[name] and RuntimeImportService._read_node_classes(folder) & set(class_types))})
            for dep in RuntimeImportService._requirements_for_node(folder):
                dependencies_by_name.setdefault(dep['package'].lower(), dep)

        referenced = sorted({value for node in workflow_nodes for value in (
            RuntimeImportService._string_values(node.get('inputs')) + RuntimeImportService._string_values(node.get('widgets_values'))
        ) if RuntimeImportService._looks_like_model(value)})
        model_index, total_models = RuntimeImportService._model_index(comfy)
        required_models: list[dict[str, Any]] = []
        missing_models: list[str] = []
        ambiguous_models: list[str] = []
        models_root = comfy / 'models'
        for reference in referenced:
            normalized = reference.replace('\\','/').lstrip('./').lower()
            matches = model_index.get(normalized) or model_index.get(Path(normalized).name.lower()) or []
            if not matches:
                # suffix match supports workflow values relative to a model subfolder.
                matches = [p for key, paths in model_index.items() if key.endswith(normalized) for p in paths]
            unique = list(dict.fromkeys(matches))
            if not unique:
                missing_models.append(reference); continue
            if len(unique) > 1: ambiguous_models.append(reference)
            file = unique[0]
            rel = file.relative_to(models_root).as_posix()
            top = rel.split('/',1)[0].lower()
            required_models.append({'name': file.name, 'model_type': MODEL_TYPE_BY_FOLDER.get(top,'other'),
                                    'source_url': None, 'target_path': rel, 'sha256': None,
                                    'strategy': 'volume', 'enabled': True, 'size_bytes': file.stat().st_size,
                                    'workflow_reference': reference, 'found': True})

        warnings = node_warnings[:]
        if not python.get('python'): warnings.append('No se detectó Python. Revisa la ruta seleccionada o el venv de Pinokio.')
        if unresolved_classes: warnings.append(f'{len(unresolved_classes)} clases no pudieron asociarse a un custom node local.')
        if missing_models: warnings.append(f'{len(missing_models)} modelos referenciados no fueron encontrados.')
        score_parts = [bool(python.get('python')), bool(python.get('torch')), not unresolved_classes, not missing_models,
                       all(n['repository'] for n in required_nodes)]
        score = round(sum(1 for x in score_parts if x) / len(score_parts) * 100)
        return {
            'source_type': source, 'selected_path': str(selected), 'comfyui_path': str(comfy),
            'comfyui_repository': repo or 'https://github.com/comfyanonymous/ComfyUI.git', 'comfyui_commit': commit,
            'python_executable': python.get('executable'), 'python_version': python.get('python'),
            'torch_version': python.get('torch'), 'torch_cuda_version': python.get('cuda'), 'gpu_name': python.get('gpu'),
            'python_candidates': python.get('candidate_attempts', []),
            'workflow': {'node_count': len(workflow_nodes), 'class_types': class_types, 'referenced_models': referenced},
            'custom_nodes': required_nodes, 'models': required_models,
            'python_dependencies': list(dependencies_by_name.values()),
            'environment_variables': [], 'volumes': [{'name':'models','mount_path':'/opt/ComfyUI/models','read_only':False}],
            'unresolved_classes': unresolved_classes, 'missing_models': missing_models, 'ambiguous_models': ambiguous_models,
            'warnings': warnings,
            'summary': {'workflow_nodes':len(workflow_nodes),'unique_classes':len(class_types),
                        'required_custom_nodes':len(required_nodes),'required_models':len(required_models),
                        'referenced_models':len(referenced),'missing_models':len(missing_models),
                        'python_dependencies':len(dependencies_by_name),'model_size_bytes':sum(m['size_bytes'] for m in required_models),
                        'installed_custom_nodes':len(node_catalog),'installed_models':total_models,'compatibility_score':score},
        }

    @staticmethod
    def scan_path(path: str, include_all_models: bool = True) -> dict[str, Any]:
        # Kept for backwards compatibility, but intentionally avoids pip-freeze and marks the result as full inventory.
        comfy, source = RuntimeImportService._find_comfy_root(Path(path))
        repo, commit = RuntimeImportService._git_info(comfy)
        python = RuntimeImportService._probe_python(comfy, Path(path))
        nodes=[]; warnings=[]
        for folder in sorted((comfy/'custom_nodes').iterdir()):
            if not folder.is_dir() or folder.name.startswith(('.', '__')): continue
            node_repo,node_commit=RuntimeImportService._git_info(folder); inferred=node_repo or RuntimeImportService._infer_repo(folder)
            nodes.append({'name':folder.name,'repository':inferred or '','commit':node_commit,'enabled':True,
                          'install_requirements':(folder/'requirements.txt').exists(),'source_path':str(folder)})
        index,total=RuntimeImportService._model_index(comfy)
        return {'source_type':source,'selected_path':str(Path(path).resolve()),'comfyui_path':str(comfy),
                'comfyui_repository':repo or 'https://github.com/comfyanonymous/ComfyUI.git','comfyui_commit':commit,
                'python_executable':python.get('executable'),'python_version':python.get('python'),'torch_version':python.get('torch'),
                'torch_cuda_version':python.get('cuda'),'gpu_name':python.get('gpu'),'custom_nodes':nodes,'models':[],
                'python_dependencies':[],'environment_variables':[],'volumes':[{'name':'models','mount_path':'/opt/ComfyUI/models','read_only':False}],
                'warnings':warnings+['Inventario general: carga un workflow para resolver únicamente sus dependencias.'],
                'summary':{'custom_nodes':len(nodes),'models':total,'model_size_bytes':0,'python_dependencies':0,
                           'git_nodes':sum(1 for n in nodes if n['repository'])}}

    @staticmethod
    def scan_inventory_zip(content: bytes) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix='tryon-comfy-import-') as temp:
            archive=Path(temp)/'inventory.zip'; archive.write_bytes(content)
            try:
                with zipfile.ZipFile(archive) as zf:
                    root=(Path(temp)/'data').resolve()
                    for member in zf.infolist():
                        target=(root/member.filename).resolve()
                        if not str(target).startswith(str(root)): raise ValueError('El ZIP contiene rutas inseguras.')
                    zf.extractall(root)
            except zipfile.BadZipFile as exc: raise ValueError('El archivo no es un ZIP válido.') from exc
            return RuntimeImportService.scan_path(str(root), False)

    @staticmethod
    def analyze_workflow(workflow: dict[str, Any], report: dict[str, Any] | None = None) -> dict[str, Any]:
        nodes=RuntimeImportService._workflow_nodes(workflow); classes=sorted({n['class_type'] for n in nodes if n['class_type']})
        refs=sorted({v for n in nodes for v in RuntimeImportService._string_values(n.get('inputs')) if RuntimeImportService._looks_like_model(v)})
        known={c for item in (report or {}).get('custom_nodes',[]) for c in item.get('matched_classes',[])}
        return {'node_count':len(nodes),'class_types':classes,'custom_node_classes':sorted(known),
                'referenced_models':refs,'potentially_missing_nodes':[],
                'summary':{'nodes':len(nodes),'unique_classes':len(classes),'referenced_models':len(refs)}}

    @staticmethod
    def apply_report(db, config: RuntimeBuilderConfig, report: dict[str, Any], selection: dict[str, bool]):
        if selection.get('base',True):
            config.comfyui_repository=report.get('comfyui_repository') or config.comfyui_repository
            config.comfyui_commit=report.get('comfyui_commit') or config.comfyui_commit
            if report.get('python_version'): config.python_version=report['python_version']
            if report.get('torch_cuda_version'): config.cuda_version=report['torch_cuda_version']
        if selection.get('custom_nodes',True):
            config.custom_nodes=[{k:v for k,v in item.items() if k in {'name','repository','commit','enabled','install_requirements'}} for item in report.get('custom_nodes',[]) if item.get('repository')]
        if selection.get('models',True):
            config.models=[{k:v for k,v in item.items() if k in {'name','model_type','source_url','target_path','sha256','strategy','enabled'}} for item in report.get('models',[])]
        if selection.get('dependencies',True):
            config.python_dependencies=[{k:v for k,v in item.items() if k in {'package','version','enabled'}} for item in report.get('python_dependencies',[])]
        if selection.get('volumes',True): config.volumes=report.get('volumes',[]) or config.volumes
        db.add(config); db.commit(); db.refresh(config); return config
