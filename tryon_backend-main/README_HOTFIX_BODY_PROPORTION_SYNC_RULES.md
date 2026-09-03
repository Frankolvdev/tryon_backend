# Hotfix — Sincronizar una categoría con reglas globales

Backend aislado para Body Proportion Tool.

Agrega:
POST /tools-generation/body-proportions/presets/{preset_id}/synchronize-rules

Comportamiento:
- Solo funciona sobre categorías base derivadas de la matriz.
- Olvida los valores guardados individualmente de esa categoría.
- Recalcula hips_size, fat_thin, breasts_size, skin_tone y hair_length usando la configuración global actual.
- Actualiza nombre/slug derivados.
- Conserva la preview y el StorageFile actuales.
- Marca el preset como draft para indicar que la preview debe regenerarse.
- No toca otros presets ni otros módulos de la plataforma.
- No requiere migración.

Git:
git add .
git commit -m "feat: add per-preset synchronization with body proportion rules"
git push
