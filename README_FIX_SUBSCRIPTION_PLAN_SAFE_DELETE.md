# Fix: eliminación segura de planes

## Problema

PostgreSQL impedía borrar físicamente un plan que todavía estaba referenciado por `user_subscriptions`, generando un error 500 por llave foránea.

## Solución

- Si el plan nunca fue utilizado, se elimina físicamente.
- Si tiene una o más suscripciones históricas o actuales, se archiva:
  - `is_active = false`
  - `is_public = false`
  - precio y producto de Stripe desactivados
  - historial y referencias preservados
- El endpoint devuelve un mensaje claro indicando si se eliminó o archivó.

No se borran suscripciones ni se modifica la llave foránea.

## Validación

```powershell
$env:PYTHONPATH = (Get-Location).Path
python -m compileall -q app tests
python -m pytest tests/test_subscription_plan_safe_delete_contract.py -v
```
