HF57 - Beam immutable runtime image + incremental build/deploy

Contenido:
- app/services/runtime_build_execution_service.py

Alcance:
- Solo agrega lógica Beam al Runtime Builder/Deploy.
- Modal y RunPod conservan sus tags, despliegues y contratos actuales.
- Al publicar un build se crea además un alias Beam inmutable: :beam-<hash>.
- Si la huella del runtime coincide, Deploy Beam usa un Dockerfile mínimo FROM <alias>.
- Si cambia un nodo, requirements, ComfyUI o runtime, la huella cambia y no se reutiliza la imagen vieja.
- El nuevo Build sigue usando la caché Docker por capas; después se publica un alias inmutable nuevo.

Aplicación:
1. Descomprimir sobre el backend.
2. Reiniciar FastAPI.
3. Para el build actual ya publicado antes de HF57, ejecutar Publicar una vez para crear el alias Beam inmutable.
4. Después, los cambios de GPU/inactividad/workers/checkpoint requieren solo Deploy.
