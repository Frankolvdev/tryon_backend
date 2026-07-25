# Backend — Seed de integración ComfyUI

Este paquete se instala en el repositorio **backend**, no en el BackOffice.

## Problema corregido

El BackOffice llamaba a los endpoints administrativos de ComfyUI, pero el backend respondía:

`Integration config not found.`

El backend obtiene la conexión de ComfyUI desde la tabla `integration_configs`, no directamente desde el `.env`.

## Cambios

### `app/core/config.py`

Agrega configuraciones ambientales con valores locales seguros:

- `COMFYUI_BASE_URL`
- `COMFYUI_WORKFLOWS_DIR`
- `COMFYUI_POLL_TIMEOUT_SECONDS`
- `COMFYUI_POLL_INTERVAL_SECONDS`

No es obligatorio modificar el `.env` para desarrollo local porque los valores por defecto apuntan a:

`http://127.0.0.1:8188`

### `app/scripts/seed.py`

El seed ahora:

- conserva la creación/sincronización del superadministrador;
- crea los defaults de `integration_configs` si faltan;
- crea o sincroniza la integración `comfyui`;
- la deja habilitada;
- configura la URL desde `COMFYUI_BASE_URL`;
- crea el directorio local de workflows;
- conserva configuraciones de nodos existentes;
- es idempotente y puede ejecutarse varias veces.

## Instalación

Extrae este ZIP directamente sobre la raíz del backend:

`F:\PROYECTOS PERSONALES\TRYON\backend`

No debe quedar una carpeta contenedora adicional.

## Ejecución

Con el entorno virtual activo:

```powershell
python -m app.scripts.seed
```

Después reinicia Uvicorn.

Ejemplo:

```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

## Verificación

1. Confirma que ComfyUI abra en:

   `http://127.0.0.1:8188`

2. Ejecuta el seed.

3. Reinicia el backend.

4. Abre el BackOffice y entra en ComfyUI.

5. La respuesta `Integration config not found.` ya no debe aparecer.

6. El endpoint de salud de ComfyUI debe consultar:

   `http://127.0.0.1:8188/system_stats`

## Docker

Cuando el backend se ejecute dentro de Docker, agrega al `.env`:

```env
COMFYUI_BASE_URL=http://host.docker.internal:8188
```

y vuelve a ejecutar el seed.

## Módulo futuro del BackOffice

La administración general de esta configuración pertenece al módulo:

**Sistema → Integraciones**

Ahí se podrán administrar ComfyUI, RunPod, S3, SMTP, Stripe y OAuth desde una interfaz común.

La pestaña Try-On consume estas integraciones para operar, pero no es el lugar principal para editar credenciales y configuración global.

## Git

```powershell
git add .
git commit -m "Backend - Seed ComfyUI integration"
git push
```
