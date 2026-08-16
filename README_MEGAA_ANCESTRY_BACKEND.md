# MegaZIP A — Ancestry Media Library (Backend)

Alcance aislado:
- Nueva tabla `ancestry_media_assets`.
- CRUD admin.
- Upload separado de poster y video.
- Storage por asset: `auto`, `local`, `amazon_s3`, `cloudflare_r2`.
- Export / import ZIP portable.
- Endpoint autenticado para AppWeb: `GET /api/v1/ancestry-assets`.
- NO modifica Body Proportions, Bubble Butt, Generation Modules ni sus servicios.

Aplicación:
```powershell
python .\APLICAR_MEGAA_ANCESTRY_BACKEND.py
python -m alembic upgrade head
```

El aplicador es estricto: aborta antes de sobrescribir archivos nuevos ya existentes o si los puntos mínimos de integración no coinciden exactamente.
