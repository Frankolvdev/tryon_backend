# Aplicación

Extrae este ZIP directamente sobre la raíz del backend:

`F:\PROYECTOS PERSONALES\TRYON\backend`

La raíz del ZIP contiene `app/`; acepta reemplazar únicamente los seis archivos incluidos.
No ejecutes ningún script PowerShell.

## Verificación

```powershell
Select-String -Path .\app\core\config.py -Pattern "TEST_FORCE_BILLING_OVERRUN|TEST_BILLING_USER_ID|TEST_BILLING_EXECUTION_ID"
python -m compileall -q app
python -c "from app.core.config import settings; print(settings.TEST_FORCE_BILLING_OVERRUN, settings.TEST_FORCE_BILLING_OVERRUN_MULTIPLIER, settings.TEST_BILLING_USER_ID)"
```
