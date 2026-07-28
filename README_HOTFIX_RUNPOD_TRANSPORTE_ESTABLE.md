# Hotfix RunPod: transporte estable y aislado

Solo reemplaza:

- `app/services/runtime_model_volume_export_service.py`

El cambio está limitado a `_copy_to_runpod()`.

## Estrategia

1. Si AWS CLI está instalado, usa `aws s3 cp` contra el endpoint S3 de RunPod.
2. Si AWS CLI no está instalado, usa boto3 Transfer Manager nativo.
3. Elimina el multipart manual que podía atascarse.
4. Verifica el tamaño remoto de cada archivo antes de continuar.
5. Modal, Beam, Local, Docker y Export Runtime permanecen sin cambios.

Para saber qué transporte se utilizó, revisa el mensaje final o el campo `transport` del resultado.
