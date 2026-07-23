MEGA22 - Runtime export duplicate Custom Nodes fix

- Deduplica Custom Nodes por ruta real antes de copiarlos.
- Usa shutil.copytree(..., dirs_exist_ok=True) como protección adicional.
- Evita contar dos veces el mismo nodo y su tamaño.
- Conserva los duplicados en el manifiesto con duplicate=true.
- Mantiene la exportación sin ZIP y las correcciones previas de Modal/requirements.
