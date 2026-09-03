BLINDAJE — RECOVERY DE CANCELACION MODAL SIN RETRIES

Este MegaZIP NO cambia código productivo.

Motivo:
Al revisar el backend actual con el nuevo orquestador async se confirmó que el
comportamiento correcto YA está implementado:

1. Una ejecución Modal running con provider_job_id NO vuelve a Redis.
2. Recovery NO llama submit/spawn.
3. Recovery NO llama cancel_call.
4. Recovery vuelve a supervisar el MISMO provider_job_id.
5. Si cancel_requested=true, provider_status=CANCEL_REQUESTED no es reemplazado
   por el heartbeat del supervisor.
6. Si el backend se apaga, solo se cancela la espera local async; NO se cancela
   ni se reinicia el FunctionCall remoto.
7. Al regresar, el mismo FunctionCall determina el desenlace real:
   - cancelado -> se cierra cancelado;
   - fallido -> se procesa el fallo;
   - completado -> entra a la semántica de finalización ya existente;
   - aún activo -> se sigue esperando el mismo job.
8. Si no existe una identidad durable recuperable, se mantiene el contrato
   fail-closed RECOVERY_FAILED / "no retry was created".

IMPORTANTE:
"Volver a observar el mismo FunctionCall ID" NO es reintentar la generación.
No se crea otro provider job.

Este paquete agrega únicamente pruebas de regresión para impedir que una futura
modificación introduzca accidentalmente spawn/cancel/requeue durante recovery.

EJECUTAR:
pytest -q tests/test_modal_cancel_recovery_no_retry_contract.py

Después ejecutar también los tests del MegaZIP anterior.
