# Backend 15E — Registrar router de Internacionalización

El archivo `app/api/v1/endpoints/admin/i18n.py` sí existe, pero no estaba importado ni registrado en:

`app/api/v1/endpoints/admin/router.py`

Por eso FastAPI respondía:

`404 Not Found`

para:

`GET /api/v1/admin/i18n/locales`

## Archivo reemplazado

- `app/api/v1/endpoints/admin/router.py`

## Cambio realizado

Se agregó:

```python
i18n,
```

al bloque de imports y:

```python
admin_router.include_router(
    i18n.router,
    tags=["Admin - Internationalization"],
)
```

al router administrativo.

## Instalación

Extrae directamente sobre:

`F:\PROYECTOS PERSONALES\TRYON\backend`

Después reinicia Uvicorn completamente.

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Prueba:

```text
http://127.0.0.1:8001/docs
```

y verifica que aparezcan las rutas `/api/v1/admin/i18n/...`.

## Git

```powershell
git add .
git commit -m "Backend - Register admin i18n router"
git push
```
