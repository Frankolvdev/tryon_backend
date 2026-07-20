HOTFIX 01C — REGISTRO / TURNSTILE

Este parche no depende del formato exacto del bloque age_confirmed.
Localiza directamente la llamada:

    user = user_repository.create(...)

e inserta inmediatamente antes:

    user_dict.pop("turnstile_token", None)

APLICACIÓN

1. Descomprime este ZIP directamente en la raíz del backend.
2. Ejecuta:

   powershell -ExecutionPolicy Bypass -File .\apply_hotfix.ps1

3. Comprueba el cambio:

   Select-String -Path app\services\user_service.py -Pattern "turnstile_token" -Context 2,3

4. Reinicia completamente el backend.
