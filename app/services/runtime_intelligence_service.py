from __future__ import annotations

import ast
import json
import os
import re
from pathlib import Path
from typing import Any

from app.services.runtime_import_service import IGNORED_DIRS, RuntimeImportService

GITHUB_RE = re.compile(r'https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?')
MODEL_HINTS = (
    'model', 'ckpt', 'checkpoint', 'unet', 'diffusion', 'vae', 'clip', 'lora',
    'control', 'adapter', 'ipadapter', 'sam', 'yolo', 'upscale', 'gguf',
    'encoder', 'detector', 'bbox', 'segm', 'embedding', 'hypernetwork',
)


class RuntimeIntelligenceService:
    """Static ComfyUI indexer. It never imports or executes custom-node code."""

    @staticmethod
    def _custom_node_roots(selected: Path, comfy: Path) -> list[Path]:
        candidates = [comfy / 'custom_nodes', selected / 'custom_nodes', selected / 'ComfyUI' / 'custom_nodes']
        base_depth = len(selected.parts)
        for current, dirs, _files in os.walk(selected):
            current_path = Path(current)
            depth = len(current_path.parts) - base_depth
            dirs[:] = [d for d in dirs if d.lower() not in IGNORED_DIRS and depth < 7]
            if current_path.name.lower() == 'custom_nodes':
                candidates.append(current_path)
                dirs[:] = []
        result: list[Path] = []
        seen: set[str] = set()
        for path in candidates:
            if not path.is_dir():
                continue
            key = str(path.resolve()).lower()
            if key not in seen:
                seen.add(key)
                result.append(path.resolve())
        return result

    @staticmethod
    def _literal_dict(node: ast.AST | None) -> dict[str, Any]:
        if node is None:
            return {}
        try:
            value = ast.literal_eval(node)
            return value if isinstance(value, dict) else {}
        except (ValueError, TypeError, SyntaxError):
            return {}

    @staticmethod
    def _mapping_entries(node: ast.AST | None) -> dict[str, str]:
        result: dict[str, str] = {}
        if not isinstance(node, ast.Dict):
            return result
        for key, value in zip(node.keys, node.values):
            if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
                continue
            target = None
            if isinstance(value, ast.Name):
                target = value.id
            elif isinstance(value, ast.Attribute):
                target = value.attr
            elif isinstance(value, ast.Constant):
                target = str(value.value)
            result[key.value] = target or key.value
        return result

    @staticmethod
    def _class_metadata(tree: ast.AST) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            meta: dict[str, Any] = {'python_class': node.name, 'category': None, 'return_types': [], 'input_fields': []}
            for item in node.body:
                if isinstance(item, (ast.Assign, ast.AnnAssign)):
                    targets = item.targets if isinstance(item, ast.Assign) else [item.target]
                    value = item.value
                    names = [target.id for target in targets if isinstance(target, ast.Name)]
                    if 'CATEGORY' in names and isinstance(value, ast.Constant):
                        meta['category'] = value.value
                    if 'RETURN_TYPES' in names:
                        try:
                            parsed = ast.literal_eval(value)
                            if isinstance(parsed, (list, tuple)):
                                meta['return_types'] = [str(v) for v in parsed]
                        except (ValueError, TypeError, SyntaxError):
                            pass
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == 'INPUT_TYPES':
                    for child in ast.walk(item):
                        if isinstance(child, ast.Dict):
                            literal = RuntimeIntelligenceService._literal_dict(child)
                            if not literal:
                                continue
                            fields: list[dict[str, Any]] = []
                            for section in ('required', 'optional', 'hidden'):
                                values = literal.get(section)
                                if isinstance(values, dict):
                                    for field, spec in values.items():
                                        fields.append({
                                            'name': str(field),
                                            'section': section,
                                            'model_hint': any(h in str(field).lower() for h in MODEL_HINTS),
                                            'spec': repr(spec)[:500],
                                        })
                            if fields:
                                meta['input_fields'] = fields
                                break
            result[node.name] = meta
        return result

    @staticmethod
    def _repo_metadata(folder: Path) -> dict[str, Any]:
        repository, commit = RuntimeImportService._git_info(folder)
        if not repository:
            repository = RuntimeImportService._infer_repo(folder)
        manifests = []
        for name in ('requirements.txt', 'pyproject.toml', 'setup.py', 'setup.cfg', 'package.json', 'install.py'):
            if (folder / name).is_file():
                manifests.append(name)
        dependencies = RuntimeImportService._requirements_for_node(folder)
        return {
            'provider': folder.name,
            'source_path': str(folder),
            'repository': repository,
            'commit': commit,
            'manifests': manifests,
            'dependencies': dependencies,
        }

    @staticmethod
    def _scan_provider(folder: Path, root: Path) -> dict[str, Any]:
        provider = RuntimeIntelligenceService._repo_metadata(folder)
        classes: dict[str, dict[str, Any]] = {}
        parse_errors: list[str] = []
        files_scanned = 0
        for file in folder.rglob('*.py'):
            if any(part.lower() in IGNORED_DIRS or part.lower() in {'env', 'venv', '.venv', 'site-packages'} for part in file.parts):
                continue
            files_scanned += 1
            try:
                text = file.read_text(encoding='utf-8', errors='ignore')
                tree = ast.parse(text, filename=str(file))
            except (OSError, SyntaxError) as exc:
                if len(parse_errors) < 25:
                    parse_errors.append(f'{file}: {exc}')
                continue
            mappings: dict[str, str] = {}
            displays: dict[str, Any] = {}
            for node in tree.body:
                if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                    continue
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                names = [target.id for target in targets if isinstance(target, ast.Name)]
                if 'NODE_CLASS_MAPPINGS' in names:
                    mappings.update(RuntimeIntelligenceService._mapping_entries(node.value))
                if 'NODE_DISPLAY_NAME_MAPPINGS' in names:
                    displays.update(RuntimeIntelligenceService._literal_dict(node.value))
            class_meta = RuntimeIntelligenceService._class_metadata(tree)
            for public_name, python_class in mappings.items():
                meta = dict(class_meta.get(python_class, {}))
                meta.update({
                    'class_type': public_name,
                    'python_class': python_class,
                    'display_name': str(displays.get(public_name) or public_name),
                    'provider': folder.name,
                    'repository': provider['repository'],
                    'commit': provider['commit'],
                    'source_file': str(file),
                    'relative_file': file.relative_to(root).as_posix(),
                    'is_loader': any(field.get('model_hint') for field in meta.get('input_fields', [])),
                })
                classes[public_name] = meta
        provider.update({
            'files_scanned': files_scanned,
            'class_count': len(classes),
            'loader_count': sum(1 for value in classes.values() if value.get('is_loader')),
            'classes': sorted(classes.values(), key=lambda item: item['class_type'].lower()),
            'parse_errors': parse_errors,
        })
        return provider

    @staticmethod
    def build_index(path: str) -> dict[str, Any]:
        selected = Path(path).expanduser().resolve()
        comfy, source_type = RuntimeImportService._find_comfy_root(selected)
        roots = RuntimeIntelligenceService._custom_node_roots(selected, comfy)
        providers: list[dict[str, Any]] = []
        class_index: dict[str, dict[str, Any]] = {}
        duplicate_classes: dict[str, list[str]] = {}
        for root in roots:
            for folder in sorted(root.iterdir()):
                if not folder.is_dir() or folder.name.startswith(('.', '__')):
                    continue
                provider = RuntimeIntelligenceService._scan_provider(folder, root)
                providers.append(provider)
                for cls in provider['classes']:
                    name = cls['class_type']
                    if name in class_index:
                        duplicate_classes.setdefault(name, [class_index[name]['provider']]).append(cls['provider'])
                    else:
                        class_index[name] = cls
        loaders = [item for item in class_index.values() if item.get('is_loader')]
        return {
            'source_type': source_type,
            'selected_path': str(selected),
            'comfyui_path': str(comfy),
            'custom_node_roots': [str(root) for root in roots],
            'providers': sorted(providers, key=lambda item: item['provider'].lower()),
            'classes': sorted(class_index.values(), key=lambda item: item['class_type'].lower()),
            'loaders': sorted(loaders, key=lambda item: item['class_type'].lower()),
            'duplicate_classes': duplicate_classes,
            'summary': {
                'custom_node_roots': len(roots),
                'providers': len(providers),
                'repositories': sum(1 for item in providers if item.get('repository')),
                'classes': len(class_index),
                'loaders': len(loaders),
                'dependencies': sum(len(item.get('dependencies', [])) for item in providers),
                'parse_errors': sum(len(item.get('parse_errors', [])) for item in providers),
                'duplicates': len(duplicate_classes),
            },
        }

    @staticmethod
    def search(index: dict[str, Any], query: str) -> list[dict[str, Any]]:
        term = query.strip().lower()
        if not term:
            return index.get('classes', [])[:200]
        return [
            item for item in index.get('classes', [])
            if term in str(item.get('class_type', '')).lower()
            or term in str(item.get('display_name', '')).lower()
            or term in str(item.get('provider', '')).lower()
        ][:200]
