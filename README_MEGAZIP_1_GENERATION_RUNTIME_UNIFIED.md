# MegaZIP 1 — Generation Runtime unificado

Este paquete extrae las primitivas compartidas del runtime sin cambiar el comportamiento externo del Backend.

## Alcance

- Mantiene los únicos tipos de paso actuales: `workflow` y `python`.
- Introduce un registro estricto de ejecutores de pasos.
- Centraliza la resolución, copia y combinación del contexto de ejecución.
- Conserva la ejecución local, simulada y RunPod existente.
- No incorpora todavía el Worker Docker/RunPod de runtime completo; eso corresponde al MegaZIP 2.

## Compatibilidad

Las rutas API, esquemas, facturación, almacenamiento, cancelación, progreso y persistencia permanecen sin cambios.

## Validaciones realizadas

- `python -m compileall -q app`
- Smoke test de resolución y combinación de contexto.
- Smoke test de despacho exclusivo de pasos `workflow` y `python`.
