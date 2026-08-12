# Models — vinculación visual con Bubble Butt

Base exacta:
tryon_backend-main - 2026-08-12T095524.287.zip

Cambio aislado:
- Añade endpoint de SOLO LECTURA:
  GET /api/v1/ai-models/body-variants/{preset_id}/bubble-butt
- Obtiene BubbleButtPreset ready que coincidan con:
  sex + fat_band + ass/hips_band del BodyProportionPreset visible.
- Devuelve únicamente las variantes Bubble Butt disponibles y su image_url.
- La imagen se resuelve con `active_preview_source`, igual que Models/AppWeb.
- No cambia generación, configuración, biblioteca, storage, perfiles ni DB.
- No hay migración.
- No modifica qué guarda actualmente "Usar este cuerpo".

Validación Python AST: OK.
