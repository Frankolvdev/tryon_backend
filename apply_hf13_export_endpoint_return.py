#!/usr/bin/env python3
"""
HF13 Backend — Corrige export_models_volume devolviendo siempre el trabajo creado.

Ejecutar desde la raíz de tryon_backend:
    python apply_hf13_export_endpoint_return.py
"""
from __future__ import annotations

from pathlib import Path
import re

ROOT = Path.cwd()
TARGET = ROOT / "app/api/v1/endpoints/admin/runtime_builder.py"

if not TARGET.exists():
    raise SystemExit(
        "No se encontró app/api/v1/endpoints/admin/runtime_builder.py. "
        "Ejecuta este archivo desde la raíz de tryon_backend."
    )

source = TARGET.read_text(encoding="utf-8")
original = source

if "HF13_EXPORT_ENDPOINT_RETURN" in source:
    print("HF13 backend ya estaba aplicado.")
    raise SystemExit(0)

# Localizar únicamente la función export_models_volume.
fn_match = re.search(
    r'(?P<header>(?:async\s+)?def\s+export_models_volume\s*\([^)]*\)(?:\s*->\s*[^:]+)?\s*:\s*\n)'
    r'(?P<body>.*?)(?=^\s*(?:async\s+)?def\s+\w+\s*\(|^\s*@router\.|\Z)',
    source,
    flags=re.MULTILINE | re.DOTALL,
)
if not fn_match:
    raise SystemExit(
        "No se encontró la función export_models_volume. No se modificó ningún archivo."
    )

header = fn_match.group("header")
body = fn_match.group("body")

# Determinar indentación del cuerpo.
indent_match = re.search(r'^([ \t]+)\S', body, flags=re.MULTILINE)
indent = indent_match.group(1) if indent_match else "    "

# Debe existir la creación del trabajo.
create_match = re.search(
    r'job\s*=\s*RuntimeContextJobService\.create_model_volume\([^)]*\)',
    body,
)
if not create_match:
    raise SystemExit(
        "No se encontró create_model_volume dentro del endpoint. "
        "No se modificó ningún archivo."
    )

# Si ya existe un return job/public al nivel de la función, no duplicarlo.
has_valid_return = re.search(
    rf'^{re.escape(indent)}return\s+(?:job|RuntimeContextJobService\.public\([^\n]+\))\s*$',
    body,
    flags=re.MULTILINE,
)

if not has_valid_return:
    # Insertar antes del final de la función, después de cualquier worker.start().
    return_block = (
        f"\n{indent}# HF13_EXPORT_ENDPOINT_RETURN\n"
        f"{indent}return RuntimeContextJobService.public(job['job_id'])\n"
    )
    body = body.rstrip() + return_block
else:
    # Marcar y normalizar para devolver el estado público más reciente.
    body = re.sub(
        rf'^{re.escape(indent)}return\s+(?:job|RuntimeContextJobService\.public\([^\n]+\))\s*$',
        (
            f"{indent}# HF13_EXPORT_ENDPOINT_RETURN\n"
            f"{indent}return RuntimeContextJobService.public(job['job_id'])"
        ),
        body,
        count=1,
        flags=re.MULTILINE,
    )

patched = source[:fn_match.start()] + header + body + source[fn_match.end():]

# Validar sintaxis antes de escribir.
compile(patched, str(TARGET), "exec")

backup = TARGET.with_suffix(TARGET.suffix + ".hf13.bak")
if not backup.exists():
    backup.write_text(original, encoding="utf-8")

TARGET.write_text(patched, encoding="utf-8")

print("HF13 backend aplicado correctamente.")
print("El endpoint export_models_volume ahora devuelve el trabajo creado.")
print("Archivo:", TARGET.relative_to(ROOT))
