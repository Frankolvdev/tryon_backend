# FIX Backend — aceptación legal persistente

- Agrega estado de aceptación por usuario.
- Agrega aceptación persistente de versiones vigentes.
- El registro por correo valida y guarda los documentos exactos aceptados.
- Los usuarios creados por OAuth, BackOffice o Backend pueden completar la aceptación al iniciar sesión.

No requiere migración Alembic.

```powershell
cd "F:\PROYECTOS PERSONALES\TRYON\backend"
.\.venv\Scripts\Activate.ps1
python -m compileall -q app
```
Reinicia el Backend.
