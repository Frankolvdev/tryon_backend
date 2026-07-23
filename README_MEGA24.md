# MEGA24 — MediaPipe build compatibility fix

Corrige el error de Docker/Modal causado por `mediapipe==0.10.0`.

Cambios:
- Normaliza la dependencia detectada `mediapipe==0.10.0` a `mediapipe==0.10.21`.
- Corrige también los `requirements.txt` dentro de Custom Nodes copiados.
- Conserva todos los arreglos anteriores de Modal Volume, requisitos PEP 508, exportación sin ZIP y deduplicación de Custom Nodes.
