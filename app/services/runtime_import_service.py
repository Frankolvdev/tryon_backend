from __future__ import annotations

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
    'upscale_models': 'upscaler', 'upscalers': 'upscaler',
}

class RuntimeImportService:
    @staticmethod
    def _run(command: list[str], cwd: Path | None = None, timeout: int = 15) -> str | None:
        try:
            result = subprocess.run(command, cwd=str(cwd) if cwd else None, capture_output=True, text=True, timeout=timeout, check=False)
            if result.returncode == 0:
                return result.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
        return None

    @staticmethod
    def _find_comfy_root(selected: Path) -> tuple[Path, str]:
        selected = selected.expanduser().resolve()
        if not selected.exists() or not selected.is_dir():
            raise ValueError('La carpeta seleccionada no existe o no es accesible por el Backend.')
        candidates = [selected, selected / 'ComfyUI', selected / 'app' / 'ComfyUI']
        for path in candidates:
            if (path / 'main.py').exists() and (path / 'custom_nodes').is_dir():
                return path, RuntimeImportService._detect_source(selected, path)
        # Pinokio and custom nested installations; bounded walk avoids model/output trees.
        ignored = {'models', 'output', 'input', '.git', 'node_modules', '__pycache__'}
        base_depth = len(selected.parts)
        for current, directories, files in os.walk(selected):
            current_path = Path(current)
            depth = len(current_path.parts) - base_depth
            directories[:] = [item for item in directories if item.lower() not in ignored and depth < 8]
            if 'main.py' in files and (current_path / 'custom_nodes').is_dir() and (current_path / 'models').is_dir():
                return current_path.resolve(), RuntimeImportService._detect_source(selected, current_path)
        raise ValueError('No se encontró una instalación válida de ComfyUI dentro de la carpeta indicada.')

    @staticmethod
    def _detect_source(selected: Path, comfy: Path) -> str:
        text = f'{selected} {comfy}'.lower()
        if 'pinokio' in text or (selected / 'pinokio.js').exists(): return 'pinokio'
        if 'stabilitymatrix' in text or 'stability matrix' in text: return 'stability-matrix'
        if (selected / 'python_embeded').exists() or (comfy.parent / 'python_embeded').exists(): return 'portable'
        if (comfy / '.git').exists(): return 'git'
        return 'custom'

    @staticmethod
    def _git_info(path: Path) -> tuple[str | None, str | None]:
        if not (path / '.git').exists(): return None, None
        return RuntimeImportService._run(['git', 'remote', 'get-url', 'origin'], path), RuntimeImportService._run(['git', 'rev-parse', 'HEAD'], path)

    @staticmethod
    def _python_executable(comfy: Path) -> Path | None:
        candidates = [
            comfy / 'venv' / 'Scripts' / 'python.exe', comfy.parent / 'venv' / 'Scripts' / 'python.exe',
            comfy.parent / 'python_embeded' / 'python.exe', comfy / 'venv' / 'bin' / 'python',
            comfy.parent / 'venv' / 'bin' / 'python',
        ]
        return next((p for p in candidates if p.exists()), None)

    @staticmethod
    def scan_path(path: str, include_all_models: bool = True) -> dict[str, Any]:
        comfy, source = RuntimeImportService._find_comfy_root(Path(path))
        repo, commit = RuntimeImportService._git_info(comfy)
        warnings: list[str] = []
        nodes: list[dict[str, Any]] = []
        for folder in sorted((comfy / 'custom_nodes').iterdir()):
            if not folder.is_dir() or folder.name.startswith(('.', '__')): continue
            node_repo, node_commit = RuntimeImportService._git_info(folder)
            requirements = (folder / 'requirements.txt').exists() or (folder / 'pyproject.toml').exists()
            if not node_repo: warnings.append(f'{folder.name}: no tiene repositorio Git detectable.')
            nodes.append({'name': folder.name, 'repository': node_repo or '', 'commit': node_commit, 'enabled': True, 'install_requirements': requirements, 'source_path': str(folder)})

        models: list[dict[str, Any]] = []
        models_root = comfy / 'models'
        if models_root.exists():
            for file in models_root.rglob('*'):
                if not file.is_file() or file.suffix.lower() not in MODEL_EXTENSIONS: continue
                rel = file.relative_to(models_root).as_posix()
                top = rel.split('/', 1)[0].lower()
                models.append({'name': file.name, 'model_type': MODEL_TYPE_BY_FOLDER.get(top, 'other'), 'source_url': None, 'target_path': rel, 'sha256': None, 'strategy': 'volume', 'enabled': include_all_models, 'size_bytes': file.stat().st_size})

        python_version = None; torch_version = None; torch_cuda = None; gpu_name = None; dependencies: list[dict[str, Any]] = []
        python = RuntimeImportService._python_executable(comfy)
        if python:
            info = RuntimeImportService._run([str(python), '-c', "import json,sys; d={'python':sys.version.split()[0]};\ntry:\n import torch; d.update(torch=torch.__version__,cuda=torch.version.cuda,gpu=(torch.cuda.get_device_name(0) if torch.cuda.is_available() else None))\nexcept Exception: pass\nprint(json.dumps(d))"], comfy, 30)
            if info:
                try:
                    parsed = json.loads(info.splitlines()[-1]); python_version=parsed.get('python'); torch_version=parsed.get('torch'); torch_cuda=parsed.get('cuda'); gpu_name=parsed.get('gpu')
                except json.JSONDecodeError: warnings.append('No se pudo interpretar la información de Python/PyTorch.')
            frozen = RuntimeImportService._run([str(python), '-m', 'pip', 'freeze', '--disable-pip-version-check'], comfy, 60)
            if frozen:
                for line in frozen.splitlines():
                    line=line.strip()
                    if not line or line.startswith(('#','-e','git+')): continue
                    match=re.match(r'^([^=<>!~\s]+)==(.+)$', line)
                    dependencies.append({'package': match.group(1) if match else line, 'version': match.group(2) if match else None, 'enabled': True})
        else:
            warnings.append('No se detectó el ejecutable Python de la instalación.')

        return {
            'source_type': source, 'selected_path': str(Path(path).resolve()), 'comfyui_path': str(comfy),
            'comfyui_repository': repo or 'https://github.com/comfyanonymous/ComfyUI.git', 'comfyui_commit': commit,
            'python_executable': str(python) if python else None, 'python_version': python_version,
            'torch_version': torch_version, 'torch_cuda_version': torch_cuda, 'gpu_name': gpu_name,
            'custom_nodes': nodes, 'models': models, 'python_dependencies': dependencies,
            'environment_variables': [], 'volumes': [{'name':'models','mount_path':'/opt/ComfyUI/models','read_only':False}],
            'warnings': warnings,
            'summary': {'custom_nodes':len(nodes),'models':len(models),'model_size_bytes':sum(m['size_bytes'] for m in models),'python_dependencies':len(dependencies),'git_nodes':sum(1 for n in nodes if n['repository'])},
        }

    @staticmethod
    def scan_inventory_zip(content: bytes) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix='tryon-comfy-import-') as temp:
            archive=Path(temp)/'inventory.zip'; archive.write_bytes(content)
            try:
                with zipfile.ZipFile(archive) as zf:
                    for member in zf.infolist():
                        target=(Path(temp)/'data'/member.filename).resolve()
                        if not str(target).startswith(str((Path(temp)/'data').resolve())): raise ValueError('El ZIP contiene rutas inseguras.')
                    zf.extractall(Path(temp)/'data')
            except zipfile.BadZipFile as exc: raise ValueError('El archivo no es un ZIP válido.') from exc
            root=Path(temp)/'data'
            # Actual lightweight ComfyUI folder zip.
            try:
                return RuntimeImportService.scan_path(str(root))
            except ValueError:
                pass
            return RuntimeImportService._parse_report_inventory(root)

    @staticmethod
    def _parse_report_inventory(root: Path) -> dict[str, Any]:
        def read(name: str) -> str:
            found=next(iter(root.rglob(name)),None); return found.read_text(encoding='utf-8-sig',errors='replace') if found else ''
        git_text=read('comfy_git.txt'); custom_text=read('custom_nodes_git.txt'); py_text=read('python_environment.txt'); torch_text=read('torch_environment.txt'); models_text=read('models_inventory.txt')
        if not any((git_text,custom_text,py_text,torch_text,models_text)): raise ValueError('El ZIP no contiene una instalación ComfyUI ni reportes de inventario reconocibles.')
        urls=re.findall(r'(?:https?://|git@)[^\s]+',git_text); hashes=re.findall(r'\b[a-f0-9]{40}\b',git_text,re.I)
        nodes=[]
        for block in re.split(r'=+\s*',custom_text):
            lines=[x.strip() for x in block.splitlines() if x.strip()]
            if not lines: continue
            name=lines[0]; repo=next((x for x in lines[1:] if x.startswith(('http','git@'))),''); commit=next((x for x in lines[1:] if re.fullmatch(r'[a-f0-9]{40}',x,re.I)),None)
            if name not in {'NO_GIT'}: nodes.append({'name':name,'repository':repo,'commit':commit,'enabled':True,'install_requirements':any('requirements.txt' in x for x in lines)})
        dependencies=[]
        for line in py_text.splitlines():
            m=re.match(r'^([^=<>!~\s]+)==(.+)$',line.strip())
            if m: dependencies.append({'package':m.group(1),'version':m.group(2),'enabled':True})
        models=[]
        try:
            raw=json.loads(models_text); raw=raw if isinstance(raw,list) else [raw]
            for item in raw:
                rel=str(item.get('RelativePath') or item.get('relative_path') or '').replace('\\','/');
                if rel: models.append({'name':Path(rel).name,'model_type':MODEL_TYPE_BY_FOLDER.get(rel.split('/')[0].lower(),'other'),'source_url':None,'target_path':rel,'sha256':None,'strategy':'volume','enabled':True,'size_bytes':int(item.get('Length') or 0)})
        except (json.JSONDecodeError,TypeError,ValueError): pass
        def find_value(key: str) -> str | None:
            m=re.search(rf'^{re.escape(key)}=(.+)$',torch_text,re.M); return m.group(1).strip() if m else None
        return {'source_type':'inventory-zip','selected_path':None,'comfyui_path':None,'comfyui_repository':urls[0] if urls else 'https://github.com/comfyanonymous/ComfyUI.git','comfyui_commit':hashes[-1] if hashes else None,'python_executable':None,'python_version':find_value('python') or None,'torch_version':find_value('torch'),'torch_cuda_version':find_value('torch_cuda'),'gpu_name':find_value('gpu'),'custom_nodes':nodes,'models':models,'python_dependencies':dependencies,'environment_variables':[],'volumes':[{'name':'models','mount_path':'/opt/ComfyUI/models','read_only':False}],'warnings':['Inventario importado desde reportes; las rutas locales no se validaron.'],'summary':{'custom_nodes':len(nodes),'models':len(models),'model_size_bytes':sum(m['size_bytes'] for m in models),'python_dependencies':len(dependencies),'git_nodes':sum(1 for n in nodes if n['repository'])}}

    @staticmethod
    def analyze_workflow(payload: dict[str, Any], report: dict[str, Any] | None = None) -> dict[str, Any]:
        nodes=[]
        if isinstance(payload.get('nodes'),list):
            for node in payload['nodes']:
                nodes.append({'id':str(node.get('id','')),'class_type':str(node.get('type') or node.get('class_type') or 'unknown'),'inputs':node.get('widgets_values') or node.get('inputs') or {}})
        else:
            for node_id,node in payload.items():
                if isinstance(node,dict) and node.get('class_type'):
                    nodes.append({'id':str(node_id),'class_type':str(node['class_type']),'inputs':node.get('inputs') or {}})
        model_names=set();
        for node in nodes:
            values=node['inputs'].values() if isinstance(node['inputs'],dict) else node['inputs'] if isinstance(node['inputs'],list) else []
            for value in values:
                if isinstance(value,str) and Path(value).suffix.lower() in MODEL_EXTENSIONS: model_names.add(value.replace('\\','/'))
        installed_names={n['name'].lower() for n in (report or {}).get('custom_nodes',[])}
        core_prefixes=('CheckpointLoader','CLIP','VAE','KSampler','Empty','SaveImage','LoadImage','PreviewImage','Latent','Conditioning','Image','Primitive','Reroute')
        custom_classes=sorted({n['class_type'] for n in nodes if not n['class_type'].startswith(core_prefixes)})
        return {'node_count':len(nodes),'class_types':sorted({n['class_type'] for n in nodes}),'custom_node_classes':custom_classes,'referenced_models':sorted(model_names),'potentially_missing_nodes':[x for x in custom_classes if not any(token in x.lower() for token in installed_names)],'summary':{'nodes':len(nodes),'unique_classes':len({n['class_type'] for n in nodes}),'referenced_models':len(model_names)}}

    @staticmethod
    def apply_report(db, config: RuntimeBuilderConfig, report: dict[str, Any], selection: dict[str,bool]) -> RuntimeBuilderConfig:
        if selection.get('base',True):
            config.comfyui_repository=report.get('comfyui_repository') or config.comfyui_repository
            config.comfyui_commit=report.get('comfyui_commit') or config.comfyui_commit
            if report.get('python_version'): config.python_version='.'.join(str(report['python_version']).split('.')[:2])
            if report.get('torch_cuda_version'): config.cuda_version=str(report['torch_cuda_version'])
        if selection.get('custom_nodes',True):
            config.custom_nodes=[{k:v for k,v in n.items() if k in {'name','repository','commit','enabled','install_requirements'}} for n in report.get('custom_nodes',[]) if n.get('repository')]
        if selection.get('models',True):
            config.models=[{k:v for k,v in m.items() if k in {'name','model_type','source_url','target_path','sha256','strategy','enabled'}} for m in report.get('models',[])]
        if selection.get('dependencies',False): config.python_dependencies=report.get('python_dependencies',[])
        if selection.get('volumes',True): config.volumes=report.get('volumes',[])
        db.add(config); db.commit(); db.refresh(config); return config
