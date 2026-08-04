# FIX Backend — Generation reset with optional gallery

Corrige el endpoint `/api/v1/admin/maintenance/generation-reset/preview` cuando la instalación no contiene la tabla opcional `user_gallery_items`.

- Detecta la tabla con el inspector de SQLAlchemy.
- Si no existe, omite únicamente la limpieza de galería.
- Continúa contabilizando y eliminando ejecuciones, jobs, datos financieros y archivos de almacenamiento.
- No requiere migración Alembic.
