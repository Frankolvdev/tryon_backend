# Body Proportion Generator V2 — Backend

Incremento aislado para `Tools Generation > Generador de proporciones corporales`.

## Alcance
- No modifica pipelines comerciales, billing, tokens, Modal, RunPod, Beam ni Runtime Engine.
- Ejecución exclusiva por ComfyUI local.
- 48 categorías base para mujer: 3 Fat x 4 Ass x 4 Breast.
- Los 13 presets Low Fat suministrados calibran las anclas de Hips/Breasts y la compensación Ass -> Breast.
- Medium/High Fat mantienen compensaciones Fat -> Hips/Breasts editables; parten en 0 porque todavía no existen muestras calibradas de esas bandas.
- Interpolación 50% entre dos presets para crear categorías intermedias.
- Límites: Hips 0..9, Breasts max 1.5, Fat/Thin -1.5..1.8, Skin -5..5.
- Storage por herramienta: `auto`, `local`, `amazon_s3`, `cloudflare_r2`.
  - `auto` consulta el StorageService global sin modificarlo.
  - Los overrides no cambian la configuración global.
- Regenerar un preset sobrescribe su archivo anterior y mantiene el mismo registro/preset.
- Espejo local por carpetas en `body-proportions-library/proportions_<sex>/...` con `preview`, `values.txt`, `values.json`.

## Aplicación
```powershell
alembic upgrade heads
```

Después iniciar el backend normalmente.
