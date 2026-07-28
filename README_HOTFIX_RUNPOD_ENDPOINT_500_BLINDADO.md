# Hotfix RunPod Endpoint 500 — aislado y blindado

## Alcance

Este hotfix modifica exclusivamente el control plane y el deploy de RunPod.
No modifica Modal, Beam, Docker build, exportador runtime, workflows, pipeline de generación ni cobros/reembolsos.

## Archivos modificados

- `app/services/runpod_control_plane_service.py`
- `app/services/runtime_build_execution_service.py`

## Correcciones

- Conserva el cuerpo real de los errores HTTP de RunPod para diagnóstico.
- Reintenta de forma limitada errores HTTP 5xx del control plane.
- Evita enviar simultáneamente `networkVolumeId` y `networkVolumeIds` para un único volumen.
- Consulta el volumen y valida que su datacenter coincida con la configuración.
- Evita crear endpoints duplicados recuperando uno existente por nombre.
- Si RunPod responde 500 al contrato completo, intenta crear con el contrato mínimo y después aplica la configuración completa mediante PATCH.
- Valida `workersMin <= workersMax` y normaliza listas/valores antes del envío.

## Pipeline y cancelación

El backend actual ya ejecuta RunPod mediante `runpod_serverless_adapter_service`:

- envío: `POST /run`
- seguimiento: `GET /status/{job_id}`
- cancelación: `POST /cancel/{job_id}`
- timeout con cancelación automática
- callback de cancelación del pipeline completo
- persistencia de `provider_job_id` y `endpoint_id`

Ese flujo se conserva intacto. No se reutiliza la API de Modal para RunPod; cada proveedor usa su API propia bajo el mismo contrato interno de ejecución.
