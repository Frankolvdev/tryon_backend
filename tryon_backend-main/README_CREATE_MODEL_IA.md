# Create Model IA — Backend, fase 1

- Nueva entidad `ai_model_profiles`, aislada del sistema actual.
- Catálogo corporal reutilizando SOLO presets Body Proportions `ready` con imagen.
- No duplica las imágenes.
- Guarda el cuerpo seleccionado por cada modelo del usuario.
- Mujer habilitada; hombre preparado pero bloqueado hasta contar con catálogo masculino.
- Migración Alembic `06c_ai_model_profiles`.

Después de aplicar:
`alembic upgrade head`
