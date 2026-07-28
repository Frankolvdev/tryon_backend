# Hotfix RunPod: multipart realmente paralelo

Este parche modifica exclusivamente `RuntimeModelVolumeExportService._copy_to_runpod`.

- No modifica Modal, Beam, Local, Docker Volume, resolvedor, Export Runtime, endpoints ni configuraciones.
- Sustituye el bucle secuencial de `upload_part` por 12 workers concurrentes.
- Cada worker abre el archivo por separado y sube una parte de 32 MiB.
- El progreso avanza únicamente cuando RunPod confirma cada parte.
