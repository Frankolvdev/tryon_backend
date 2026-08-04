# FIX — Bloqueo de generación por configuración incompleta

## Objetivo

Impedir que una generación normal o una prueba administrativa cree un trabajo cuando no es posible calcular de forma segura su costo y tokens.

## Validaciones

Antes de cobrar tokens, persistir la ejecución o enviarla a la cola se comprueba:

- módulo activo;
- regla de pricing existente, activa y vinculada al módulo;
- duración estimada inicial positiva;
- margen técnico no negativo;
- ganancia USD no negativa;
- valor comercial del token configurado y positivo;
- proveedor habilitado y con credenciales/endpoints mínimos;
- GPU seleccionada;
- tiempo de permanencia/idle del proveedor;
- precio activo USD/segundo para la GPU seleccionada.

## Comportamiento

Si falta algo, el backend responde HTTP 409 con:

- código: `GENERATION_MODULE_MISSING_CONFIGURATION`
- mensaje: `Este módulo de generación no está disponible temporalmente. Contacta con soporte. Falta configuración necesaria.`

No cobra tokens, no crea ejecución y no llama al proveedor.

La ejecución de prueba del BackOffice pasa por la misma validación, pero mantiene `user_id=None`, por lo que sigue sin cobrar tokens.

## Archivos

- `app/services/generation_configuration_readiness_service.py`
- `app/services/generation_module_runtime_service.py`
- `tests/test_generation_configuration_readiness_contract.py`

## Pruebas

```powershell
$env:PYTHONPATH = (Get-Location).Path
python -m pytest tests/test_generation_configuration_readiness_contract.py -v
python -m pytest tests -v
```
