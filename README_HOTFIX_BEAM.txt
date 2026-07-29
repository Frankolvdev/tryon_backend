HOTFIX BEAM - SUBIDA PARALELA SEGURA EN WINDOWS

Alcance:
- Solo modifica la implementación Beam.
- Modal, RunPod, Docker y el resto del backend permanecen intactos.

Corrección:
- Nunca usa beam://volumen/carpeta como destino de subida en Windows.
- Cada archivo se sube primero a beam://volumen y luego se mueve con beam mv.
- Reutiliza una sola autenticación por lote.
- Exporta hasta 3 archivos en paralelo.
- El contador usa exclusivamente los archivos reales del árbol preparado.
- El File Manager usa el mismo transporte seguro raíz + move.
