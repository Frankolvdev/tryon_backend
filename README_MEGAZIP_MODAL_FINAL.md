# MegaZIP Modal — integración completa del runtime exportado

Este ZIP corrige la integración desde la fuente del Runtime Builder.

## Incluye

- El `modal_app.py` generado expone `POST /api/tryon/pipeline`.
- Agrega `GET /api/tryon/runtime` para verificar el contrato desplegado.
- Copia automáticamente `runpod_worker/generation_runtime` al contexto exportado.
- El `Dockerfile.modal` incorpora ese runtime dentro de `/app/runtime/runpod_worker`.
- Valida que la exportación Modal no pueda completarse sin el endpoint y el ejecutor.
- Conserva el contrato `tryon.generation-runtime/v1`.
- Mantiene la ejecución completa de pasos Workflow y Python.
- Mantiene el transporte base64 de entradas y resultados.
- Materializa y persiste en el backend las salidas devueltas por Modal.
- Relaciona estados de pasos por `step_key` para evitar desalineación si hay pasos deshabilitados.

## Después de aplicar

1. Reinicia el backend.
2. Exporta nuevamente el runtime desde el BackOffice.
3. Compila y despliega el runtime exportado en Modal.
4. Verifica `GET <URL_MODAL>/api/tryon/runtime`.
5. Ejecuta el módulo con `Motor = Modal`.

No reutilices una exportación anterior: debe generarse una nueva para incluir el ejecutor completo.
