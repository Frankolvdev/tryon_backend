# FIX — Modal Runtime Exact Telemetry

## Alcance

Este ZIP es incremental sobre el backend actualizado del 3 de agosto de 2026.

Añade telemetría exacta al resultado del Generation Runtime sin reescribir ni sustituir:

- `run_pipeline` existente;
- cancelaciones Modal;
- `FunctionCall` y recuperación tras reinicio;
- ComfyUI embebido;
- GPU Snapshot y Runtime Engine;
- HTTP/WebSocket proxy;
- Beam;
- RunPod.

## Métrica usada para el cobro

Cuando el Runtime devuelve métricas:

```text
duration_source = runtime_exact
real_provider_duration_ms = execution_time_ms del Runtime
```

El backend ya no reemplaza ese valor con `started_at → finished_at`.

El cálculo comercial continúa siendo:

```text
segundos facturables = tiempo real + scaledown configurado + margen técnico
```

No se espera `container_exit` para entregar el resultado.

## Cancelaciones y fallos abruptos

Si Modal cancela o mata la FunctionCall antes de que pueda devolver métricas, no existe un resultado exacto del Runtime. En ese caso se usa la mejor medición persistida posible y se etiqueta claramente:

- `provider_observed_cancelled`
- `provider_observed_fallback`
- `backend_fallback`

Así nunca se presenta una aproximación como si fuera una métrica exacta.

## Aplicación

Descomprimir sobre la raíz del backend.

```powershell
$env:PYTHONPATH = (Get-Location).Path
python -m pytest tests/test_modal_runtime_exact_billing_contract.py -v
python -m pytest tests -v
```

## Runtime Modal

Este cambio modifica el código que el Runtime Builder introduce en la imagen Modal. Después de aplicar y validar el backend es obligatorio:

1. Generar nuevamente el runtime autocontenido de Modal.
2. Compilar la imagen.
3. Hacer nuevamente el deploy de Modal.

No es necesario cambiar el workflow ni volver a configurar modelos residentes.
