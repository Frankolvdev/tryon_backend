Fix aislado Body Proportions:
- BackOffice preview ahora resuelve desde config.storage_mode (destino de nuevas generaciones).
- AppWeb/Create Model IA sigue usando active_preview_source.
- Fallback legacy a image_storage_file_id para no romper presets existentes.
No se modifica la arquitectura multi-source ni otros módulos.
