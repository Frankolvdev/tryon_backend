ALCANCE BLINDADO — MODELS IA

Este ZIP es INCREMENTAL: contiene únicamente archivos nuevos o modificados para este alcance.
No reemplaza carpetas completas. Copia el contenido respetando las rutas.

BLINDAJE:
- Ancestry existente NO fue modificado.
- No se tocaron workers, motores Modal/RunPod/Beam, pagos, auth, storage global ni otros módulos.
- AppWeb solo cambia la vista FaceStudio de selección de identidad y estilos asociados.

DESPUÉS DE COPIAR:
1) Activa tu .venv.
2) Ejecuta: python -m alembic upgrade heads
3) Reinicia el backend.

Se agrega una tabla nueva model_generation_assets. El export/import global empaqueta Ancestry existente + Eyebrows/Lips/Hairstyle sin alterar el servicio Ancestry.
