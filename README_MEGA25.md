# MEGA25 — Modal path + production dependency filter

Cambios incrementales:
- Normaliza el Volume de Modal a `/app/ComfyUI/models`.
- Corrige rutas heredadas `/opt/ComfyUI/models` y `/models`.
- Elimina dependencias de desarrollo del runtime (`black`, `flake8`, `pytest`, etc.).
- Aplica el mismo filtro a los `requirements.txt` copiados dentro de Custom Nodes.
- Conserva la normalización `mediapipe==0.10.0` → `mediapipe==0.10.21`.
