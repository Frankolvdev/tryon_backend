#!/usr/bin/env python3
"""
HF12D — Repara la sintaxis dañada por HF12 en runtime_builder.py.

Ejecutar desde la raíz de tryon_backend:

    python apply_hf12d_backend_syntax_repair.py
"""
from __future__ import annotations

from pathlib import Path
import re

ROOT = Path.cwd()
TARGET = ROOT / "app/api/v1/endpoints/admin/runtime_builder.py"

if not TARGET.exists():
    raise SystemExit(
        "No se encontró app/api/v1/endpoints/admin/runtime_builder.py. "
        "Ejecuta este instalador desde la raíz de tryon_backend."
    )

source = TARGET.read_text(encoding="utf-8")
original = source

broken = (
    "job = RuntimeContextJobService.create_model_volume(config.id, payload) "
    "RuntimeContextJobService._update(job['job_id'], status='queued', "
    "phase='starting', progress=1, "
    "message='Iniciando exportación de modelos…') "
    "job = RuntimeContextJobService.public(job['job_id'])"
)

fixed = (
    "job = RuntimeContextJobService.create_model_volume(config.id, payload)\n"
    "    RuntimeContextJobService._update(\n"
    "        job['job_id'],\n"
    "        status='queued',\n"
    "        phase='starting',\n"
    "        progress=1,\n"
    "        message='Iniciando exportación de modelos…',\n"
    "    )\n"
    "    job = RuntimeContextJobService.public(job['job_id'])"
)

if broken in source:
    source = source.replace(broken, fixed, 1)
else:
    pattern = re.compile(
        r"job\s*=\s*RuntimeContextJobService\.create_model_volume\(config\.id,\s*payload\)\s+"
        r"RuntimeContextJobService\._update\(job\[['\"]job_id['\"]\],\s*status=['\"]queued['\"],\s*"
        r"phase=['\"]starting['\"],\s*progress=1,\s*"
        r"message=['\"]Iniciando exportación de modelos…['\"]\)\s+"
        r"job\s*=\s*RuntimeContextJobService\.public\(job\[['\"]job_id['\"]\]\)"
    )
    match = pattern.search(source)
    if match:
        source = source[:match.start()] + fixed + source[match.end():]
    elif "HF12D_BACKEND_SYNTAX_REPAIR" in source:
        print("HF12D ya estaba aplicado.")
        raise SystemExit(0)
    else:
        raise SystemExit(
            "No se encontró la línea dañada esperada. "
            "No se modificó ningún archivo."
        )

# Añadir marcador sin afectar ejecución.
source = source.replace(
    "job = RuntimeContextJobService.create_model_volume(config.id, payload)\n",
    "# HF12D_BACKEND_SYNTAX_REPAIR\n"
    "    job = RuntimeContextJobService.create_model_volume(config.id, payload)\n",
    1,
)

# Validar ANTES de escribir.
compile(source, str(TARGET), "exec")

backup = TARGET.with_suffix(TARGET.suffix + ".hf12d.bak")
if not backup.exists():
    backup.write_text(original, encoding="utf-8")

TARGET.write_text(source, encoding="utf-8")

print("HF12D aplicado correctamente.")
print("Archivo reparado:", TARGET.relative_to(ROOT))
print("La sintaxis fue validada antes de guardar.")
