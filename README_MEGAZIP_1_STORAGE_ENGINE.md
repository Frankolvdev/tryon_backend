# MegaZIP 1 — Backend Multi-Provider Storage Engine

## Alcance

Motor de almacenamiento por archivo con tres proveedores para archivos nuevos:

- `local`
- `amazon_s3`
- `cloudflare_r2`

Los registros históricos con `provider = s3` conservan la configuración S3 histórica y no se mueven.
Cambiar `storage_provider` solo afecta archivos nuevos.

## Operaciones centralizadas

- carga de bytes y UploadFile
- lectura/materialización
- URL firmada
- descarga/stream administrativo
- eliminación física
- prueba de conexión
- Try-On local y RunPod
- entradas dinámicas para Modal, Beam y RunPod
- limpieza de generaciones mediante el proveedor original

## Migración

```powershell
alembic upgrade head
```

La migración crea configuraciones independientes para Amazon S3 y Cloudflare R2. No modifica ni mueve archivos existentes.

## Valores permitidos de `storage_provider`

```text
local
amazon_s3
cloudflare_r2
```

El valor histórico `s3` se acepta como alias de selección para Amazon, pero los archivos ya guardados como `s3` continúan ligados a la integración histórica `s3`.

## Configuración Amazon S3

Integración `amazon_s3`:

- `api_key`: Access Key ID
- `api_secret`: Secret Access Key
- `config.bucket`
- `config.region`
- `config.endpoint_url` opcional
- `config.public_base_url` opcional
- `config.addressing_style`: `virtual` recomendado

## Configuración Cloudflare R2

Integración `cloudflare_r2`:

- `api_key`: Access Key ID de R2
- `api_secret`: Secret Access Key de R2
- `config.account_id`
- `config.bucket`
- `config.endpoint_url` opcional; se deriva del Account ID
- `config.public_base_url` opcional para dominio público/personalizado
- `config.addressing_style`: `path`

## Validación

```powershell
$env:PYTHONPATH = (Get-Location).Path
python -m compileall -q app alembic/versions tests
python -m pytest tests/test_multi_provider_storage_contract.py -v
```

Resultado durante generación: `4 passed`.

## Endpoints preparados para BackOffice

```text
GET  /api/v1/admin/storage/providers
POST /api/v1/admin/storage/providers/{provider}/health
```

Los endpoints existentes de listado, contenido, URL firmada y eliminación permanecen vigentes.
