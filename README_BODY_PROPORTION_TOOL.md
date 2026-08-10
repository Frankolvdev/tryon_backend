# Tools Generation · Body Proportion Generator — Backend

Módulo nuevo y aislado. No modifica el pipeline comercial, billing, jobs, Modal, RunPod, Beam, Runtime Builder ni los módulos de generación existentes.

## Qué agrega
- Configuración separada de workflow API de ComfyUI para `woman` y `man`.
- Ejecución exclusivamente mediante `comfyui_local_adapter_service`.
- Tabla de perfiles corporales con valores numéricos como fuente de verdad.
- Escalera dinámica: perfiles arbitrarios, inserción intermedia y siguiente nivel compensado.
- Límites configurables. Defaults solicitados: hips 0..9, breasts max 1.5, fat_thin -1.5..1.8, skin -5..5. El mínimo de breasts queda sin forzar porque no fue definido y los presets existentes ya usan valores negativos.
- Al regenerar una fila, la imagen anterior se reemplaza.
- Imagen persistida mediante el `StorageService` ya existente, respetando el proveedor activo.
- Espejo local adicional en `LOCAL_STORAGE_DIR/body-proportions-library/proportions_<sex>/profile_xxx/` con `preview.*`, `values.txt` y `values.json`.

## Fórmula de siguiente escalón
La vista permite configurar:
- `fat_step`
- `hips_step`
- `breasts_step`
- `fat_to_hips`
- `fat_to_breasts`
- `hips_to_breasts`

Cálculo:
- `fat_new = fat + fat_step`
- `hips_delta = hips_step + fat_to_hips * fat_step`
- `breasts_delta = breasts_step + fat_to_breasts * fat_step + hips_to_breasts * hips_delta`

Si el resultado supera límites, el backend rechaza la creación.

## Aplicación
Copiar los archivos del ZIP sobre la raíz del backend y ejecutar:

```powershell
alembic upgrade heads
```

Después iniciar el backend normalmente.

## Workflow API
El BackOffice permite cargar el JSON API de ComfyUI y mapear cada valor a `node_id + input_name`:
- hips_size
- fat_thin
- breasts_size
- skin_tone
- hair_length
- category_name (opcional)
- sex (opcional, woman=True / man=False)
