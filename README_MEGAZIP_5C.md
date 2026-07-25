# MegaZIP 5C — Endpoint Modal generado desde Runtime Builder

Este parche modifica la fuente del Runtime Builder.

Cada nueva exportación Modal genera `modal_app.py` con:

- `POST /api/tryon/pipeline`
- contrato `tryon.generation-runtime/v1`
- `GET /api/tryon/runtime` para diagnóstico
- validación de exportación que impide generar un runtime Modal sin el endpoint obligatorio

## Después de aplicar

1. Reinicia el backend.
2. Regenera/exporta el runtime desde BackOffice.
3. Compila y despliega nuevamente en Modal.
4. Comprueba `GET <URL_MODAL>/api/tryon/runtime`.
5. Ejecuta el módulo con `Motor = Modal`.
