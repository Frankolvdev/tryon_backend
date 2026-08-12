# Bubble Butt — Etapa 2 Body Proportions

Base exacta:
- tryon_backend-main - 2026-08-11T222542.970.zip

Alcance incremental:
- Nueva configuración/workflow Bubble Butt por sexo.
- Segundo workflow ComfyUI totalmente independiente del workflow Body Proportions.
- Mapeos propios: hips_size, fat_thin, breasts_size, bubble_butt, skin_tone,
  hair_length, category_name y sex.
- Exactamente 3 valores globales bubble_butt por cada combinación Fat x Hips.
- Las bandas Fat y anclas Hips se derivan dinámicamente de Body Proportions,
  incluidos futuros intermedios.
- breasts_size usa SIEMPRE el ancla explícita `huge` de Breast, con las
  compensaciones Fat/Hips vigentes para esa fila.
- Bubble Butt queda bloqueado hasta que toda la malla BASE de Body Proportions
  esté `ready` y tenga preview en el proveedor configurado para generar.
- Generación Bubble Butt hereda `storage_mode` de Body Proportions.
- Copias multi-provider Local/R2/S3 independientes para Bubble Butt.
- La biblioteca copiar/verificar/exportar/importar incorpora Bubble Butt.
- configuration.json versionado incluye configuración global Body Proportions
  + Bubble Butt.
- Guardar configuración actualiza el configuration.json del espejo local.
- Copiar biblioteca escribe configuration.json también en el proveedor destino.
- Exportar ZIP incluye configuration.json.
- Importar ZIP aplica configuraciones globales y restaura Body + Bubble Butt.
- Preparado por `sex` para incorporar Hombre sin rehacer la arquitectura.

Blindaje:
- No se reutiliza la tabla BodyProportionPreset para Bubble Butt.
- No se modifica la semántica del workflow Body Proportions existente.
- No se modifica billing, generación comercial, Runtime Engine, Modal,
  RunPod, Beam, usuarios ni otros módulos.

IMPORTANTE:
Ejecutar migración antes de levantar el backend:
    alembic upgrade head

Validaciones realizadas:
- Python compileall/AST: OK.
