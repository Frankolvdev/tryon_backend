#!/usr/bin/env python3
"""
HF12 Backend — Inicio inmediato y observable del exportador de modelos.

Ejecutar desde la raíz de tryon_backend:

    python apply_hf12_model_export_job_start.py
"""
from __future__ import annotations

from pathlib import Path
import re

ROOT = Path.cwd()
TARGET = ROOT / "app/api/v1/endpoints/admin/runtime_builder.py"

if not TARGET.exists():
    raise SystemExit(
        "No se encontró app/api/v1/endpoints/admin/runtime_builder.py. "
        "Ejecuta el instalador desde la raíz de tryon_backend."
    )

source = TARGET.read_text(encoding="utf-8")
original = source

if "HF12_MODEL_EXPORT_THREAD" in source:
    print("HF12 backend ya estaba aplicado.")
    raise SystemExit(0)

# Añadir import threading de forma compatible con archivo normal o minificado.
if re.search(r'(^|\s)import threading(\s|$)', source) is None:
    if source.startswith("from fastapi import"):
        source = "import threading\n" + source
    else:
        source = "import threading\n" + source

old = (
    "background_tasks.add_task(RuntimeContextJobService.run_model_volume, job['job_id']) "
    "return job"
)

new = (
    "# HF12_MODEL_EXPORT_THREAD: iniciar fuera del ciclo de respuesta para que "
    "# el endpoint 202 regrese inmediatamente y el polling pueda observar progreso. "
    "worker = threading.Thread("
    "target=RuntimeContextJobService.run_model_volume, "
    "args=(job['job_id'],), "
    "name=f\"runtime-model-export-{job['job_id'][:8]}\", "
    "daemon=True"
    ") "
    "worker.start() "
    "return job"
)

if old not in source:
    # Variante con espacios/saltos.
    pattern = re.compile(
        r"background_tasks\.add_task\(\s*"
        r"RuntimeContextJobService\.run_model_volume\s*,\s*"
        r"job\[['\"]job_id['\"]\]\s*\)\s*"
        r"return\s+job"
    )
    match = pattern.search(source)
    if not match:
        raise SystemExit(
            "No se encontró el arranque BackgroundTasks del exportador de modelos. "
            "No se modificó ningún archivo."
        )
    source = source[:match.start()] + new + source[match.end():]
else:
    source = source.replace(old, new, 1)

# Marcar el trabajo como iniciado justo antes de arrancar el hilo.
needle = "job = RuntimeContextJobService.create_model_volume(config.id, payload)"
replacement = (
    "job = RuntimeContextJobService.create_model_volume(config.id, payload) "
    "RuntimeContextJobService._update("
    "job['job_id'], "
    "status='queued', "
    "phase='starting', "
    "progress=1, "
    "message='Iniciando exportación de modelos…'"
    ") "
    "job = RuntimeContextJobService.public(job['job_id'])"
)

if needle in source:
    source = source.replace(needle, replacement, 1)
elif "message='Iniciando exportación de modelos…'" not in source:
    raise SystemExit(
        "No se encontró la creación del trabajo de exportación. "
        "No se modificó ningún archivo."
    )

if "HF12_MODEL_EXPORT_THREAD" not in source:
    raise SystemExit("Validación HF12 backend fallida: no quedó el marcador.")

backup = TARGET.with_suffix(TARGET.suffix + ".hf12.bak")
if not backup.exists():
    backup.write_text(original, encoding="utf-8")

TARGET.write_text(source, encoding="utf-8")
compile(source, str(TARGET), "exec")

print("HF12 backend aplicado.")
print("Modificado:", TARGET.relative_to(ROOT))
print("Respaldo:", backup.relative_to(ROOT))
