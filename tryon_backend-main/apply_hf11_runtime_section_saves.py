#!/usr/bin/env python3
"""
HF11 — Guardado independiente por sección + guardado global.

Ejecutar desde la raíz de tryon_backoffice:

    python apply_hf11_runtime_section_saves.py

Modifica únicamente:
    src/components/runtime-builder/runtime-mega3-panel.tsx
"""
from __future__ import annotations

from pathlib import Path
import re
import sys

ROOT = Path.cwd()
TARGET = ROOT / "src/components/runtime-builder/runtime-mega3-panel.tsx"

if not TARGET.exists():
    raise SystemExit(
        "No se encontró src/components/runtime-builder/runtime-mega3-panel.tsx. "
        "Ejecuta este instalador desde la raíz de tryon_backoffice."
    )

source = TARGET.read_text(encoding="utf-8")
original = source

if "const saveExportConfiguration=async" in source:
    print("HF11 ya estaba aplicado.")
    raise SystemExit(0)

# ---------------------------------------------------------------------------
# 1) Sustituir el guardado único por tres funciones:
#    - saveExportConfiguration
#    - saveRuntimeConfiguration
#    - saveAllConfiguration
# ---------------------------------------------------------------------------

save_pattern = re.compile(
    r'const save=async\(\)=>\{'
    r'if\(!settings\)return;'
    r'setBusy\(true\);'
    r'try\{'
    r'const \[savedSettings,savedLaunch\]=await Promise\.all\(\['
    r'browserApiRequest(?:<RuntimeModelExportSettings>)?\('
    r'"/api/admin/runtime-builder/models-volume/settings",'
    r'\{method:"PUT",body:JSON\.stringify\(settings\)\}\),'
    r'browserApiRequest(?:<RuntimeLaunchSettings>)?\('
    r'"/api/admin/runtime-builder/runtime-launch/settings",'
    r'\{method:"PUT",body:JSON\.stringify\(launch\)\}\)'
    r'\]\);'
    r'setSettings\(savedSettings\);'
    r'setLaunch\(savedLaunch\);'
    r'toast\.success\("Configuración persistida\."\)'
    r'\}catch\(e\)\{'
    r'toast\.error\(e instanceof Error\?e\.message:"No se pudo guardar\."\)'
    r'\}finally\{setBusy\(false\)\}'
    r'\};'
)

replacement = (
    'const saveExportConfiguration=async(showToast=true)=>{'
    'if(!settings)return false;'
    'setBusy(true);'
    'try{'
    'const savedSettings=await browserApiRequest<RuntimeModelExportSettings>('
    '"/api/admin/runtime-builder/models-volume/settings",'
    '{method:"PUT",body:JSON.stringify(settings)}'
    ');'
    'setSettings(savedSettings);'
    'if(showToast)toast.success("Configuración de exportación guardada.");'
    'return true'
    '}catch(e){'
    'toast.error(e instanceof Error?e.message:"No se pudo guardar la configuración de exportación.");'
    'return false'
    '}finally{setBusy(false)}'
    '}; '
    'const saveRuntimeConfiguration=async(showToast=true)=>{'
    'setBusy(true);'
    'try{'
    'const savedLaunch=await browserApiRequest<RuntimeLaunchSettings>('
    '"/api/admin/runtime-builder/runtime-launch/settings",'
    '{method:"PUT",body:JSON.stringify(launch)}'
    ');'
    'setLaunch(savedLaunch);'
    'if(showToast)toast.success("Runtime Configuration guardada.");'
    'return true'
    '}catch(e){'
    'toast.error(e instanceof Error?e.message:"No se pudo guardar Runtime Configuration.");'
    'return false'
    '}finally{setBusy(false)}'
    '}; '
    'const saveAllConfiguration=async(showToast=true)=>{'
    'if(!settings)return false;'
    'setBusy(true);'
    'try{'
    'const [savedSettings,savedLaunch]=await Promise.all(['
    'browserApiRequest<RuntimeModelExportSettings>('
    '"/api/admin/runtime-builder/models-volume/settings",'
    '{method:"PUT",body:JSON.stringify(settings)}'
    '),'
    'browserApiRequest<RuntimeLaunchSettings>('
    '"/api/admin/runtime-builder/runtime-launch/settings",'
    '{method:"PUT",body:JSON.stringify(launch)}'
    ')'
    ']);'
    'setSettings(savedSettings);'
    'setLaunch(savedLaunch);'
    'if(showToast)toast.success("Toda la configuración fue guardada.");'
    'return true'
    '}catch(e){'
    'toast.error(e instanceof Error?e.message:"No se pudo guardar toda la configuración.");'
    'return false'
    '}finally{setBusy(false)}'
    '};'
)

match = save_pattern.search(source)
if not match:
    raise SystemExit(
        "No se encontró la función save() esperada. "
        "El repositorio pudo cambiar después de generar este Hotfix; no se modificó ningún archivo."
    )

source = source[:match.start()] + replacement + source[match.end():]

# ---------------------------------------------------------------------------
# 2) La exportación debe guardar todo antes de iniciar, sin toast duplicado.
# ---------------------------------------------------------------------------

source, count_run = re.subn(
    r'await save\(\);const created=',
    'const saved=await saveAllConfiguration(false);if(!saved)throw new Error("No se pudo guardar la configuración antes de exportar.");const created=',
    source,
    count=1,
)
if count_run != 1:
    raise SystemExit(
        "No se encontró la llamada await save() del flujo de exportación. "
        "No se modificó ningún archivo."
    )

# ---------------------------------------------------------------------------
# 3) Convertir el botón existente de la sección de exportación.
# ---------------------------------------------------------------------------

button_pattern = re.compile(
    r'<Btn onClick=\{\(\)=>void save\(\)\} disabled=\{busy\}>'
    r'<Save className="size-4"/>\s*Guardar configuración\s*</Btn>'
)

export_button = (
    '<Btn onClick={()=>void saveExportConfiguration()} disabled={busy}>'
    '<Save className="size-4"/>'
    'Guardar exportación'
    '</Btn>'
)

source, count_button = button_pattern.subn(export_button, source, count=1)

# Compatibilidad con formato ligeramente diferente/minificado.
if count_button != 1:
    source, count_button = re.subn(
        r'onClick=\{\(\)=>void save\(\)\} disabled=\{busy\}>'
        r'\s*<Save className="size-4"/>\s*Guardar configuración',
        'onClick={()=>void saveExportConfiguration()} disabled={busy}>'
        '<Save className="size-4"/>Guardar exportación',
        source,
        count=1,
    )

if count_button != 1:
    raise SystemExit(
        "No se encontró el botón Guardar configuración de la sección de exportación. "
        "No se modificó ningún archivo."
    )

# ---------------------------------------------------------------------------
# 4) Añadir botón propio a Runtime Configuration.
#
# Se inserta antes del bloque 'Docker Run Preview', que pertenece a la misma
# tarjeta/sección y existe en la versión actual del repositorio.
# ---------------------------------------------------------------------------

runtime_button = (
    '<div className="flex flex-wrap items-center gap-3">'
    '<Btn onClick={()=>void saveRuntimeConfiguration()} disabled={busy}>'
    '<Save className="size-4"/>'
    'Guardar Runtime Configuration'
    '</Btn>'
    '</div>'
)

marker = '<div className="rounded-2xl border border-white/10 bg-black/20 p-4"><div className="mb-3 flex items-center justify-between"><span className="text-sm font-semibold text-white">Docker Run Preview</span>'

if marker in source:
    source = source.replace(marker, runtime_button + marker, 1)
else:
    # Variante tolerante: insertar antes del contenedor que contiene el texto.
    preview_pattern = re.compile(
        r'(<div[^>]*>\s*<div[^>]*>\s*<span[^>]*>\s*Docker Run Preview\s*</span>)',
        re.DOTALL,
    )
    source, count_preview = preview_pattern.subn(runtime_button + r'\1', source, count=1)
    if count_preview != 1:
        raise SystemExit(
            "No se encontró el bloque Docker Run Preview para insertar el botón "
            "de Runtime Configuration. No se modificó ningún archivo."
        )

# ---------------------------------------------------------------------------
# 5) Añadir botón global al inicio del panel, antes de la primera sección.
# ---------------------------------------------------------------------------

global_button = (
    '<div className="mb-5 flex justify-end">'
    '<button type="button" onClick={()=>void saveAllConfiguration()} disabled={busy} '
    'className="inline-flex h-11 items-center gap-2 rounded-xl bg-red-700 px-5 '
    'text-sm font-semibold text-white transition hover:bg-red-600 disabled:opacity-50">'
    '<Save className="size-4"/>'
    'Guardar toda la configuración'
    '</button>'
    '</div>'
)

# La versión actual retorna un fragmento con dos secciones.
# Insertamos tras el fragmento de apertura y antes del primer article.
source, count_global = re.subn(
    r'(if\(!settings\)return\s*<div[^;]+;</div>;\s*return\s*<>)',
    r'\1' + global_button,
    source,
    count=1,
    flags=re.DOTALL,
)

if count_global != 1:
    # Variante minificada: primer "<article" después de "return<>".
    idx_return = source.find("return<>")
    idx_article = source.find("<article", idx_return if idx_return >= 0 else 0)
    if idx_return >= 0 and idx_article >= 0:
        source = source[:idx_article] + global_button + source[idx_article:]
        count_global = 1

if count_global != 1:
    raise SystemExit(
        "No se encontró el inicio del panel para insertar el botón global. "
        "No se modificó ningún archivo."
    )

# ---------------------------------------------------------------------------
# Validaciones
# ---------------------------------------------------------------------------

required = (
    "const saveExportConfiguration=async",
    "const saveRuntimeConfiguration=async",
    "const saveAllConfiguration=async",
    "Guardar exportación",
    "Guardar Runtime Configuration",
    "Guardar toda la configuración",
    "await saveAllConfiguration(false)",
)

missing = [item for item in required if item not in source]
if missing:
    raise SystemExit("Validación HF11 fallida: " + ", ".join(missing))

if "void save()" in source or "await save();" in source:
    raise SystemExit("Validación HF11 fallida: quedaron referencias a save().")

backup = TARGET.with_suffix(TARGET.suffix + ".hf11.bak")
if not backup.exists():
    backup.write_text(original, encoding="utf-8")

TARGET.write_text(source, encoding="utf-8")

print("HF11 aplicado correctamente.")
print("Archivo modificado:", TARGET.relative_to(ROOT))
print("Respaldo:", backup.relative_to(ROOT))
print()
print("Acciones disponibles:")
print("- Guardar exportación")
print("- Guardar Runtime Configuration")
print("- Guardar toda la configuración")
