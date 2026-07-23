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
    'diffusion_models': 'diffusion_model', 'unet': 'diffusion_model', 'unets': 'diffusion_model',
    'text_encoders': 'clip', 'animatediff_models': 'video_model',
}
IGNORED_DIRS = {'models', 'output', 'input', '.git', 'node_modules', '__pycache__', '.cache', 'temp'}
UUID_RE = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$')
MODEL_INPUT_RULES = {
    'UNETLoader': (('unet_name','diffusion_model',('diffusion_models','unet','unets')),),
    'CheckpointLoaderSimple': (('ckpt_name','checkpoint',('checkpoints',)),),
    'CheckpointLoader': (('ckpt_name','checkpoint',('checkpoints',)),),
    'CLIPLoader': (('clip_name','clip',('text_encoders','clip')),),
    'DualCLIPLoader': (('clip_name1','clip',('text_encoders','clip')),('clip_name2','clip',('text_encoders','clip'))),
    'TripleCLIPLoader': (('clip_name1','clip',('text_encoders','clip')),('clip_name2','clip',('text_encoders','clip')),('clip_name3','clip',('text_encoders','clip'))),
    'VAELoader': (('vae_name','vae',('vae',)),),
    'LoraLoader': (('lora_name','lora',('loras','lora')),),
    'LoraLoaderModelOnly': (('lora_name','lora',('loras','lora')),),
    'ControlNetLoader': (('control_net_name','controlnet',('controlnet',)),),
    'DiffControlNetLoader': (('control_net_name','controlnet',('controlnet',)),),
    'UpscaleModelLoader': (('model_name','upscaler',('upscale_models','upscalers')),),
    'CLIPVisionLoader': (('clip_name','clip',('clip_vision',)),),
    'StyleModelLoader': (('style_model_name','other',('style_models',)),),
    'GLIGENLoader': (('gligen_name','other',('gligen',)),),
    'unCLIPCheckpointLoader': (('ckpt_name','checkpoint',('checkpoints',)),),
}
MODEL_FIELD_HINTS = ('model','ckpt','checkpoint','unet','diffusion','vae','clip','lora','control','adapter','ipadapter','sam','yolo','ultralytics','upscale','gguf','encoder','detector','bbox','segm')
CORE_FALLBACK_CLASSES = {
    'CheckpointLoaderSimple','CheckpointLoader','unCLIPCheckpointLoader','UNETLoader','CLIPLoader','DualCLIPLoader','TripleCLIPLoader','VAELoader',
    'LoraLoader','LoraLoaderModelOnly','ControlNetLoader','DiffControlNetLoader','CLIPVisionLoader','StyleModelLoader','GLIGENLoader','UpscaleModelLoader',
    'LoadImage','LoadImageMask','SaveImage','PreviewImage','ImageScale','ImageScaleBy','ImageInvert','ImageBatch','ImagePadForOutpaint','EmptyImage',
    'EmptyLatentImage','EmptySD3LatentImage','EmptyLatentAudio','LatentUpscale','LatentUpscaleBy','LatentComposite','LatentBlend','LatentFlip','LatentCrop',
    'KSampler','KSamplerAdvanced','SamplerCustom','SamplerCustomAdvanced','RandomNoise','BasicScheduler','KarrasScheduler','ExponentialScheduler','PolyexponentialScheduler',
    'CFGGuider','BasicGuider','DualCFGGuider','FluxGuidance','ConditioningCombine','ConditioningConcat','ConditioningAverage','ConditioningSetArea','ConditioningSetMask',
    'CLIPTextEncode','CLIPSetLastLayer','CLIPTextEncodeSDXL','CLIPTextEncodeSDXLRefiner','VAEDecode','VAEEncode','VAEEncodeForInpaint','InpaintModelConditioning',
    'ModelMergeSimple','ModelMergeBlocks','ModelMergeAdd','ModelSamplingDiscrete','ModelSamplingContinuousEDM','ModelSamplingFlux','FreeU','FreeU_V2',
    'ControlNetApply','ControlNetApplyAdvanced','SetLatentNoiseMask','RepeatLatentBatch','RebatchLatents','ImageToMask','MaskToImage','SolidMask','InvertMask','CropMask',
    'FeatherMask','GrowMask','MaskComposite','PorterDuffImageComposite','SplitImageWithAlpha','JoinImageWithAlpha','ImageCompositeMasked','ImageBlend','ImageBlur',
    'ImageQuantize','ImageSharpen','ImageColorToMask','ImageOnlyCheckpointLoader','PhotoMakerLoader','PhotoMakerEncode','DifferentialDiffusion','StableCascade_EmptyLatentImage',
    'StableCascade_StageB_Conditioning','SDTurboScheduler','AlignYourStepsScheduler','LCMScheduler','HyperTile','PatchModelAddDownscale','VideoLinearCFGGuidance',
}



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
        # Pinokio may place env beside app/ or several levels above it.
        for root in roots:
            if not root.exists(): continue
            base_depth = len(root.parts)
            for current, dirs, files in os.walk(root):
                current_path = Path(current)
                depth = len(current_path.parts) - base_depth
                dirs[:] = [d for d in dirs if d.lower() not in IGNORED_DIRS and depth < 9]
                parent = current_path.name.lower()
                if 'python.exe' in files and parent in {'scripts', 'python_embeded', 'python', 'bin'}:
                    candidates.append(current_path / 'python.exe')
                if 'python' in files and parent in {'bin', 'venv', '.venv', 'env', 'python'}:
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
        seen_objects: set[int] = set()
        def visit(value: Any) -> None:
            if isinstance(value, dict):
                marker=id(value)
                if marker in seen_objects: return
                seen_objects.add(marker)
                if 'class_type' in value and isinstance(value.get('class_type'), str):
                    cls=str(value.get('class_type') or '')
                    if cls and not UUID_RE.match(cls):
                        result.append({'id':str(value.get('id','')),'class_type':cls,'inputs':value.get('inputs') or {},'widgets_values':value.get('widgets_values') or [],'title':(value.get('_meta') or {}).get('title') if isinstance(value.get('_meta'),dict) else None})
                elif 'type' in value and ('widgets_values' in value or 'inputs' in value or 'outputs' in value):
                    cls=str(value.get('type') or '')
                    if cls and not UUID_RE.match(cls):
                        result.append({'id':str(value.get('id','')),'class_type':cls,'inputs':value.get('inputs') or {},'widgets_values':value.get('widgets_values') or [],'title':value.get('title')})
                for child in value.values(): visit(child)
            elif isinstance(value,list):
                for child in value: visit(child)
        visit(workflow)
        dedup={}
        for node in result: dedup[(node['id'],node['class_type'])]=node
        return list(dedup.values())

    @staticmethod
    def _runtime_node_catalog(comfy: Path, python_executable: str | None) -> dict[str, dict[str, Any]]:
        if not python_executable: return {}
        script="\n".join([
            "import inspect,json,os,sys", "sys.path.insert(0, os.getcwd())", "result={}",
            "try:", " import nodes", " try: nodes.init_extra_nodes(init_custom_nodes=True)",
            " except TypeError: nodes.init_extra_nodes()", " except Exception: pass",
            " for name, cls in getattr(nodes,'NODE_CLASS_MAPPINGS',{}).items():",
            "  try: f=inspect.getsourcefile(cls) or inspect.getfile(cls)", "  except Exception: f=None",
            "  result[str(name)]={'file':f,'module':getattr(cls,'__module__',None)}",
            "except Exception as e: result={'__error__':{'message':str(e)}}", "print(json.dumps(result))"])
        output=RuntimeImportService._run([python_executable,'-c',script],comfy,120)
        if not output: return {}
        try:
            data=json.loads(output.splitlines()[-1]); return data if isinstance(data,dict) else {}
        except json.JSONDecodeError: return {}

    @staticmethod
    def _core_static_classes(comfy: Path) -> set[str]:
        classes:set[str]=set()
        for file in comfy.rglob('*.py'):
            if 'custom_nodes' in file.parts or any(part in IGNORED_DIRS for part in file.parts): continue
            try: text=file.read_text(encoding='utf-8',errors='ignore')
            except OSError: continue
            for match in re.finditer(r'NODE_CLASS_MAPPINGS\s*=\s*\{(.*?)\}',text,re.S):
                classes.update(re.findall(r"['\"]([^'\"]+)['\"]\s*:",match.group(1)))
        return classes

    @staticmethod
    def _model_references_for_node(node: dict[str, Any]) -> list[dict[str,str]]:
        cls=node.get('class_type',''); inputs=node.get('inputs') if isinstance(node.get('inputs'),dict) else {}; refs=[]
        for field,model_type,folders in MODEL_INPUT_RULES.get(cls,()):
            value=inputs.get(field)
            if isinstance(value,str): refs.append({'value':value,'field':field,'model_type':model_type,'folders':','.join(folders),'class_type':cls})
        for field,value in inputs.items():
            if isinstance(value,str) and (RuntimeImportService._looks_like_model(value) or any(h in field.lower() for h in MODEL_FIELD_HINTS)):
                if not any(r['value']==value for r in refs): refs.append({'value':value,'field':field,'model_type':'other','folders':'','class_type':cls})
        for value in RuntimeImportService._string_values(node.get('widgets_values')):
            if RuntimeImportService._looks_like_model(value) and not any(r['value']==value for r in refs):
                refs.append({'value':value,'field':'widgets_values','model_type':'other','folders':'','class_type':cls})
        return refs

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
        selected=Path(path).expanduser().resolve(); comfy,source=RuntimeImportService._find_comfy_root(selected)
        repo,commit=RuntimeImportService._git_info(comfy); python=RuntimeImportService._probe_python(comfy,selected)
        workflow_nodes=RuntimeImportService._workflow_nodes(workflow)
        class_types=sorted({n['class_type'] for n in workflow_nodes if n['class_type'] and not UUID_RE.match(n['class_type'])})
        runtime_catalog=RuntimeImportService._runtime_node_catalog(comfy,python.get('executable'))
        core_classes=RuntimeImportService._core_static_classes(comfy) | CORE_FALLBACK_CLASSES; class_to_folder={}; custom_root=comfy/'custom_nodes'
        folders=[f for f in sorted(custom_root.iterdir() if custom_root.exists() else []) if f.is_dir() and not f.name.startswith(('.', '__'))]
        for folder in folders:
            for cls in RuntimeImportService._read_node_classes(folder): class_to_folder.setdefault(cls,folder)

        # Consult the Intelligence Index directly. The previous MegaZIP exposed an
        # index endpoint, but the workflow resolver did not consume its result.
        # Building the static index here keeps resolution deterministic and also
        # supports Pinokio installations with more than one custom_nodes folder.
        intelligence_by_name: dict[str, dict[str, Any]] = {}
        intelligence_summary: dict[str, Any] = {}
        try:
            from app.services.runtime_intelligence_service import RuntimeIntelligenceService
            intelligence = RuntimeIntelligenceService.build_index(str(selected))
            intelligence_summary = intelligence.get('summary') or {}
            for item in intelligence.get('classes') or []:
                if not isinstance(item, dict):
                    continue
                public_name = str(item.get('class_type') or '').strip()
                display_name = str(item.get('display_name') or '').strip()
                python_class = str(item.get('python_class') or '').strip()
                for alias in (public_name, display_name, python_class):
                    if alias:
                        intelligence_by_name.setdefault(alias.casefold(), item)
                source_file = item.get('source_file')
                if public_name and source_file:
                    source_path = Path(str(source_file)).resolve()
                    provider_path = Path(str(item.get('source_path') or source_path.parent)).resolve()
                    class_to_folder.setdefault(public_name, provider_path)
                    if display_name:
                        class_to_folder.setdefault(display_name, provider_path)
        except Exception as exc:
            intelligence_summary = {'error': str(exc)}
        for cls,meta in runtime_catalog.items():
            if cls=='__error__' or not isinstance(meta,dict) or not meta.get('file'): continue
            try: file_path=Path(meta['file']).resolve()
            except OSError: continue
            try:
                rel=file_path.relative_to(custom_root.resolve())
                if rel.parts: class_to_folder[cls]=custom_root/rel.parts[0]
            except ValueError: core_classes.add(cls)
        required_folders={}; unresolved_classes=[]; resolved_classes=[]
        virtual_workflow_nodes = {'getnode', 'setnode', 'reroute', 'note'}
        for cls in class_types:
            folder=class_to_folder.get(cls)
            intel = intelligence_by_name.get(cls.casefold())
            # Some extensions create a deterministic class name by appending a
            # SHA-256 suffix (for example ExecutePython<64 hex chars>).
            if intel is None:
                normalized = re.sub(r'[0-9a-f]{64}$', '', cls, flags=re.IGNORECASE).casefold()
                intel = intelligence_by_name.get(normalized)
                if intel is None and normalized:
                    intel = next((value for key, value in intelligence_by_name.items() if key == normalized or key.startswith(normalized)), None)
            if folder is None and intel and intel.get('source_file'):
                source_file = Path(str(intel['source_file'])).resolve()
                candidate = Path(str(intel.get('source_path') or source_file.parent)).resolve()
                folder = candidate
            if folder:
                required_folders[str(folder).casefold()]=folder
                resolved_classes.append({'class_type':cls,'provider':'custom','provider_name':str(intel.get('provider') if intel else folder.name),'confidence':'intelligence-index' if intel else ('runtime' if cls in runtime_catalog else 'static')})
            elif intel:
                resolved_classes.append({'class_type':cls,'provider':'custom','provider_name':str(intel.get('provider') or 'Custom Node'),'confidence':'intelligence-index'})
            elif cls.casefold() in virtual_workflow_nodes:
                resolved_classes.append({'class_type':cls,'provider':'workflow','provider_name':'ComfyUI Frontend / Extension','confidence':'workflow-virtual'})
            elif cls in core_classes or cls in runtime_catalog or cls in MODEL_INPUT_RULES:
                resolved_classes.append({'class_type':cls,'provider':'core','provider_name':'ComfyUI Core','confidence':'runtime' if cls in runtime_catalog else 'knowledge-base'})
            else: unresolved_classes.append(cls)
        required_nodes=[]; dependencies_by_name={}; node_warnings=[]
        for _folder_key,folder in sorted(required_folders.items(), key=lambda item: str(item[1]).lower()):
            name=folder.name
            node_repo,node_commit=RuntimeImportService._git_info(folder); inferred=node_repo or RuntimeImportService._infer_repo(folder)
            matched=sorted(cls for cls in class_types if class_to_folder.get(cls)==folder)
            if not inferred: node_warnings.append(f'{name}: se detectó localmente, pero no se encontró repositorio.')
            required_nodes.append({'name':name,'repository':inferred or '','commit':node_commit,'enabled':True,'install_requirements':(folder/'requirements.txt').exists() or (folder/'pyproject.toml').exists(),'source_path':str(folder),'confidence':'exact-git' if node_repo else ('inferred-readme' if inferred else 'local-only'),'matched_classes':matched})
            for dep in RuntimeImportService._requirements_for_node(folder): dependencies_by_name.setdefault(dep['package'].lower(),dep)
        reference_records=[]
        for node in workflow_nodes: reference_records.extend(RuntimeImportService._model_references_for_node(node))
        unique_refs={}
        for ref in reference_records: unique_refs[(ref['value'].replace('\\','/').lower(),ref['class_type'],ref['field'])]=ref
        reference_records=list(unique_refs.values()); referenced=sorted({r['value'] for r in reference_records})
        model_index,total_models=RuntimeImportService._model_index(comfy); required_models=[]; missing_models=[]; ambiguous_models=[]; models_root=comfy/'models'
        for ref in reference_records:
            reference=ref['value']; normalized=reference.replace('\\','/').lstrip('./').lower()
            matches=model_index.get(normalized) or model_index.get(Path(normalized).name.lower()) or []
            if not matches: matches=[p for key,paths in model_index.items() if key.endswith('/'+normalized) or key.endswith(normalized) for p in paths]
            unique=list(dict.fromkeys(matches))
            if not unique: missing_models.append(reference); continue
            if len(unique)>1: ambiguous_models.append(reference)
            file=unique[0]; rel=file.relative_to(models_root).as_posix(); top=rel.split('/',1)[0].lower()
            inferred_type=ref['model_type'] if ref['model_type']!='other' else MODEL_TYPE_BY_FOLDER.get(top,'other')
            required_models.append({'name':file.name,'model_type':inferred_type,'source_url':None,'target_path':rel,'sha256':None,'strategy':'volume','enabled':True,'size_bytes':file.stat().st_size,'workflow_reference':reference,'resolver':{'class_type':ref['class_type'],'field':ref['field'],'folders':ref['folders']},'found':True})
        warnings=node_warnings[:]
        if not python.get('python'): warnings.append('No se detectó Python. Se revisaron venv/.venv/env/python_embeded y rutas anidadas de Pinokio.')
        if unresolved_classes: warnings.append(f'{len(unresolved_classes)} clases siguen sin resolver tras consultar ComfyUI, NODE_CLASS_MAPPINGS y reglas conocidas.')
        if missing_models: warnings.append(f'{len(set(missing_models))} modelos referenciados no fueron encontrados.')
        weighted_total=max(1,len(class_types)+len(reference_records)+4)
        weighted_ok=(len(class_types)-len(unresolved_classes))+(len(reference_records)-len(set(missing_models)))+sum(bool(python.get(k)) for k in ('python','torch','cuda','gpu'))
        score=max(0,min(100,round(weighted_ok/weighted_total*100)))
        return {'source_type':source,'selected_path':str(selected),'comfyui_path':str(comfy),'comfyui_repository':repo or 'https://github.com/comfyanonymous/ComfyUI.git','comfyui_commit':commit,'python_executable':python.get('executable'),'python_version':python.get('python'),'torch_version':python.get('torch'),'torch_cuda_version':python.get('cuda'),'gpu_name':python.get('gpu'),'python_candidates':python.get('candidate_attempts',[]),'workflow':{'node_count':len(workflow_nodes),'class_types':class_types,'referenced_models':referenced},'resolved_classes':resolved_classes,'core_classes':[r['class_type'] for r in resolved_classes if r['provider']=='core'],'custom_nodes':required_nodes,'models':required_models,'python_dependencies':list(dependencies_by_name.values()),'environment_variables':[],'volumes':[{'name':'models','mount_path':'/opt/ComfyUI/models','read_only':False}],'unresolved_classes':unresolved_classes,'missing_models':sorted(set(missing_models)),'ambiguous_models':sorted(set(ambiguous_models)),'warnings':warnings,'summary':{'workflow_nodes':len(workflow_nodes),'unique_classes':len(class_types),'core_classes':sum(1 for r in resolved_classes if r['provider']=='core'),'resolved_custom_classes':sum(1 for r in resolved_classes if r['provider']=='custom'),'required_custom_nodes':len(required_nodes),'required_models':len(required_models),'referenced_models':len(reference_records),'missing_models':len(set(missing_models)),'python_dependencies':len(dependencies_by_name),'model_size_bytes':sum(m['size_bytes'] for m in required_models),'installed_custom_nodes':len(folders),'installed_models':total_models,'runtime_catalog_classes':max(0,len(runtime_catalog)-int('__error__' in runtime_catalog)),'knowledge_base_rules':len(MODEL_INPUT_RULES),'intelligence_index_classes':int(intelligence_summary.get('classes') or 0),'intelligence_index_providers':int(intelligence_summary.get('providers') or 0),'compatibility_score':score}}

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
