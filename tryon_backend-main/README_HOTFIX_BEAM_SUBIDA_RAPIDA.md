# Hotfix Beam: subida rápida tipo Modal

## Alcance

Este parche modifica únicamente la implementación Beam. Modal, RunPod, Docker y los demás proveedores no se modifican.

## Cambios

- Limpia el staging local de Beam antes de cada exportación para no arrastrar modelos de exportaciones anteriores.
- Exporta el árbol completo de modelos con un único `beam cp`, evitando un proceso `cp` + `mv` por archivo.
- El contador refleja exclusivamente los archivos existentes en el staging limpio actual.
- El File Manager sube directamente a `beam://volumen/ruta-final` con una sola transferencia.
- Elimina la copia local temporal, la subida a la raíz y el movimiento remoto de cada archivo.

## Aplicación

Descomprimir directamente sobre la raíz del backend y reiniciar Uvicorn.
