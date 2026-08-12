# Bubble Butt — ajuste incremental 4 variantes

Base exacta:
tryon_backend-main - 2026-08-11T231112.220.zip

Cambios ÚNICOS:
- Bubble Butt ahora tiene 4 variantes.
- Defaults: V1=0.0, V2=0.4, V3=0.8, V4=1.2.
- Compatibilidad con configuración legacy de 3 valores:
  - [0,0,0] -> nuevos defaults.
  - valores custom de 3 posiciones -> se preservan como V2/V3/V4 y se antepone V1=0.
- La malla genera 4 presets por cada Fat x Hips.
- Protección backend de una sola ejecución simultánea compartida entre
  Body Proportions y Bubble Butt.
- Importación de configuration.json acepta el nuevo arreglo de 4 valores.
- Reset Bubble Butt:
  - checkbox DESMARCADO: elimina datos/imágenes pero conserva workflow + mappings Bubble Butt.
  - checkbox MARCADO: elimina también la configuración/workflow/mappings Bubble Butt.
  - valores Bubble Butt vuelven a 0 / 0.4 / 0.8 / 1.2.

No hay nueva migración en este fix.
La columna existente es JSON y no cambia su esquema.

Validación:
- Python AST: OK
- Python compileall: OK
