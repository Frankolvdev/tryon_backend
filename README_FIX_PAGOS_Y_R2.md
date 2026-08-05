# FIX Backend — Pagos por alcance y diagnóstico Cloudflare R2

## Corrige

1. `BillingHistoryService.list_payments()` acepta `record_scope` y lo envía al repositorio real.
2. Los campos comerciales de pagos (intento/pago, descuento, cupón y conciliación) se construyen en el servicio que usa la API.
3. Cloudflare R2 ya no toma un dominio público como endpoint S3.
4. La prueba de R2 valida acceso real al bucket mediante `list_objects_v2(MaxKeys=1)`.
5. Los errores 404 y 401/403 muestran mensajes claros sobre bucket, Account ID, jurisdicción, credenciales y permisos.

## Configuración correcta de R2

- Account ID: el identificador de la cuenta Cloudflare.
- Bucket: nombre exacto del bucket, sin URL ni prefijos.
- Access Key ID y Secret Access Key: credenciales S3 de R2.
- Endpoint S3 normal: `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`.
- Bucket EU: `https://<ACCOUNT_ID>.eu.r2.cloudflarestorage.com`.
- Bucket FedRAMP: `https://<ACCOUNT_ID>.fedramp.r2.cloudflarestorage.com`.
- Dominio público: se configura como URL pública/CDN, nunca como endpoint S3.

## Aplicación

```powershell
cd "F:\PROYECTOS PERSONALES\TRYON\backend"

.\.venv\Scripts\Activate.ps1

python -m compileall -q app tests
python -m pytest tests/test_payments_scope_and_r2_health_contract.py tests/test_storage_provider_activation_guard_contract.py -v
```

No requiere migración Alembic. Reinicia completamente el Backend.

## Git

```powershell
git add .
git commit -m "fix: restore payment scopes and improve R2 diagnostics"
git push
```
