#!/usr/bin/env python3
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

text = TARGET.read_text(encoding="utf-8")
original = text

replacement = '''@router.put('/runtime-launch/settings', response_model=RuntimeLaunchSettings)
def update_runtime_launch_settings(payload: RuntimeLaunchSettings, db: Session = Depends(get_db)):
    config = get_or_create(db)
    values = payload.model_dump()

    # Runtime Configuration es la única fuente de verdad para los nombres.
    # Se conservan estos campos internos para compatibilidad con los
    # exportadores y compiladores existentes.
    config.name = payload.build_name
    config.runtime_name = payload.build_name
    config.registry_image = payload.image_name

    _save_mega3_settings(db, config, "runtime_launch", values)

    # La respuesta se construye desde lo realmente persistido.
    stored = dict(_mega3_settings(config).get("runtime_launch") or {})
    return RuntimeLaunchSettings.model_validate(stored)
'''

pattern = re.compile(
    r"@router\.put\('/runtime-launch/settings',\s*response_model=RuntimeLaunchSettings\)\s*"
    r"def\s+update_runtime_launch_settings\(payload:\s*RuntimeLaunchSettings,\s*"
    r"db:\s*Session\s*=\s*Depends\(get_db\)\):\s*"
    r"config\s*=\s*get_or_create\(db\)\s*"
    r"_save_mega3_settings\(db,\s*config,\s*[\"']runtime_launch[\"'],\s*payload\.model_dump\(\)\)\s*"
    r"return\s+payload",
    re.MULTILINE,
)

if "RuntimeLaunchSettings.model_validate(stored)" in text:
    print("HF10 backend ya estaba aplicado.")
    raise SystemExit(0)

match = pattern.search(text)
if not match:
    raise SystemExit(
        "No se encontró el bloque esperado de update_runtime_launch_settings. "
        "No se modificó ningún archivo."
    )

text = text[:match.start()] + replacement.rstrip() + text[match.end():]

backup = TARGET.with_suffix(TARGET.suffix + ".hf10.bak")
if not backup.exists():
    backup.write_text(original, encoding="utf-8")

TARGET.write_text(text, encoding="utf-8")
compile(text, str(TARGET), "exec")

for required in (
    "config.runtime_name = payload.build_name",
    "config.registry_image = payload.image_name",
    "RuntimeLaunchSettings.model_validate(stored)",
):
    if required not in text:
        TARGET.write_text(original, encoding="utf-8")
        raise SystemExit(f"Validación fallida: {required}")

print("HF10 backend aplicado correctamente.")
print("Modificado:", TARGET.relative_to(ROOT))
print("Respaldo:", backup.relative_to(ROOT))
