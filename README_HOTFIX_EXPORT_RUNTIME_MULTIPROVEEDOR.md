# Hotfix Export Runtime multiproveedor

Restaura el contrato funcional del exportador original de Modal y lo adapta a perfiles múltiples.

## Regla restaurada

Export Runtime consume exclusivamente `config.models` del perfil seleccionado. No vuelve a ejecutar el resolvedor del workflow.

## Proveedores

- Modal: genera su configuración Modal y usa el nombre de Volume Modal solamente para perfiles `provider=modal`.
- RunPod Serverless: comparte la preparación del contexto, usando los valores persistidos de su perfil.
- Beam: comparte la preparación del contexto, usando los valores persistidos de su perfil.
- Local: comparte la preparación del contexto, usando los valores persistidos de su perfil.

## Archivos

- `app/services/runtime_builder_service.py`
- `app/services/runtime_context_generator_service.py`
- `app/services/runtime_context_job_service.py`

No modifica el resolvedor de workflows ni el exportador de modelos a volúmenes.
