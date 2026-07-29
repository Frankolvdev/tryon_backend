# HOTFIX Beam: mismo venv del backend y exportación de modelos

## Alcance

- Beam SDK/CLI se instala y utiliza desde el mismo entorno virtual del backend.
- El backend ya no crea, instala ni actualiza entornos Beam externos.
- La exportación comprueba/crea el volumen antes de copiar.
- Los archivos se suben uno a uno con destinos `beam://` normalizados con `/`.
- Modal y los demás proveedores no se modifican.

## Aplicación

Con el venv del backend activado:

```powershell
pip install -r requirements.txt
```

Reiniciar Uvicorn después de completar la instalación.
