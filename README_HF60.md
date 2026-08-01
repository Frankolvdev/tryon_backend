# HF60 — Beam Immutable Incremental Runtime Images

## Alcance

Este parche modifica únicamente la rama de build/deploy de Beam en `RuntimeBuildExecutionService`.

No modifica Modal, RunPod, `beam_worker/app.py`, AppWeb, cancelación, resultados, rutas de modelos ni el runtime compartido.

## Comportamiento

- Calcula una huella de contenido del runtime exportado.
- Usa una etiqueta inmutable `:beam-<huella>` en el registro configurado en Runtime Builder.
- Si esa huella ya fue publicada, el deploy usa un contexto mínimo y no sincroniza `custom_nodes`.
- Si cambió un nodo o archivo del runtime, crea una nueva imagen Beam con caché Docker local, publica la nueva etiqueta y luego hace deploy mínimo.
- Nunca vuelve silenciosamente al build remoto de horas dentro de Beam.

## Requisito único

`Imagen del registro` debe apuntar a un repositorio real y Docker debe tener sesión iniciada con permisos de escritura. No puede usar `ghcr.io/your-org/...`.

## Flujo esperado

- Configuración (GPU, inactividad, workers, checkpoint): solo Deploy.
- Cambio de nodo/runtime: Deploy construye incrementalmente la nueva imagen Beam, la publica y despliega.
- Primer uso: construye/publica una vez; los siguientes deploys de la misma huella son mínimos.
