HOTFIX encapsulado: solo optimiza la subida de modelos a RunPod Serverless.

- Conserva Modal, Beam, Local, Docker Volume y Export Runtime sin cambios.
- Sustituye el multipart secuencial de 32 MiB por boto3 S3Transfer concurrente.
- Usa hasta 8 partes simultáneas de 64 MiB.
- Mantiene reintentos, comprobación de archivos existentes y progreso/ETA.
- El contador se etiqueta como "archivo físico" porque un modelo lógico compuesto (por ejemplo SAM3) puede requerir varios archivos físicos.
