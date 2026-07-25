# MEGAZIP 1 — Runtime Builder Foundation

## Contenido

Este paquete contiene dos ZIP incrementales independientes:

- `backend_runtime_builder_foundation.zip`: modelos, migración, schemas, validación, generación de Dockerfile/manifiestos y endpoints administrativos.
- `backoffice_runtime_builder_foundation.zip`: módulo gráfico Runtime Builder, navegación, editores de ComfyUI, Custom Nodes, modelos, dependencias, variables, volúmenes y previsualización de archivos.

Cada ZIP se descomprime directamente sobre la raíz del repositorio correspondiente, sin carpeta raíz adicional.

## Endpoints nuevos

- `GET /api/v1/admin/runtime-builder/config`
- `PUT /api/v1/admin/runtime-builder/config`
- `POST /api/v1/admin/runtime-builder/validate`
- `POST /api/v1/admin/runtime-builder/generate`

## Ruta nueva del BackOffice

- `/dashboard/runtime-builder`

## Backend

```powershell
alembic upgrade head
python -m compileall app
uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

## BackOffice

```powershell
Remove-Item -Recurse -Force .next -ErrorAction SilentlyContinue
npm install
npm run build
npm run dev
```

## Git Backend

```powershell
git add .
git commit -m "feat: add runtime builder foundation"
git push
```

## Git BackOffice

```powershell
git add .
git commit -m "feat: add graphical runtime builder"
git push
```

## Alcance del MegaZIP 1

Este MegaZIP prepara y valida la configuración, y genera de forma reproducible:

- Dockerfile
- entrypoint.sh
- runtime-manifest.json
- custom-nodes.lock.json
- models-manifest.json
- .env.example

El MegaZIP 2 agregará construcción real, logs de build, publicación en registro, pruebas del contenedor y activación/despliegue hacia RunPod.
