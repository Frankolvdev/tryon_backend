# MegaZIP 1 — Backend: resiliencia y pricing dinámico

## Alcance

Este paquete es incremental y conserva los contratos actuales de AppWeb y BackOffice mientras añade la base del nuevo sistema:

- Modal reutiliza el `provider_job_id` persistido después de reiniciar el backend.
- Una ejecución `running` nunca vuelve a `queued` durante recuperación.
- Si no puede reanudarse de forma segura, queda `failed` y no se crea otro trabajo.
- El resultado recuperado entra por el mismo procesamiento normal existente.
- Se conservan `started_at`, estados y `execution_id` originales.
- Máquina de estados interna sin renombrar los estados públicos existentes.
- Reglas de pricing con ganancia fija USD, duración inicial y margen técnico.
- Costos editables por proveedor/GPU.
- Simulación de reglas aplicadas a módulos.
- Promedio histórico recortado de las últimas ejecuciones completadas.
- Tiempo real y fotografía inmutable del desglose de cobro en cada ejecución.
- Reconciliación sincrónica de tokens antes de exponer el estado final.
- Cancelaciones y fallos contabilizan el consumo observado cuando existe precio de GPU configurado.

## Migración

```powershell
alembic upgrade head
```

La migración es:

```text
04a_dyn_pricing_resilience
```

## Pruebas

```powershell
$env:PYTHONPATH = (Get-Location).Path
python -m pytest tests/test_megazip_dynamic_pricing_resilience_contract.py -v
python -m pytest tests -v
```

## Prueba crítica de recuperación Modal

1. Iniciar una generación y confirmar que ya existe `provider_job_id`.
2. Detener el backend con `Ctrl+C`.
3. Reiniciar el backend.
4. Debe aparecer `[backend-modal-resume]` con el mismo `call_id`.
5. No debe aparecer un segundo `[backend-modal-spawn-created]` para ese `execution_id`.
6. Si Modal ya terminó, el resultado debe pasar por el flujo normal y quedar `completed`.

## Compatibilidad

No se modificaron los adaptadores Beam ni RunPod. Los campos comerciales antiguos siguen presentes durante la migración de las interfaces.

## Precisión de tiempos

Para éxitos se prioriza la suma de tiempos reales de los pasos devueltos por el runtime. Para cancelaciones o fallos sin resultado completo se utiliza el tiempo observado desde el inicio original preservado. El cobro comercial suma el `scaledown` configurado y el margen técnico; no espera el apagado físico del contenedor.
