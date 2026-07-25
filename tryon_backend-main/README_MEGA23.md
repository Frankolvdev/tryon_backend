MEGA23 - Detección interna de Modal Volume

Cambios:
- Detecta Modal aunque todavía no exista selector visual de proveedor.
- Reconoce Modal por plataforma, notas, variables RUNTIME_PROVIDER/modal o Volume configurado con modelos de estrategia volume.
- Si "Copiar modelos" está desactivado y existe Volume, fuerza la generación de:
  - modal_app.py
  - extra_model_paths.yaml
- Marca runtime.json con provider=modal y model_storage=external-volume.
- Mantiene el fix de Custom Nodes duplicados y la exportación sin ZIP gigante.

Aplicar sobre la raíz del backend.
