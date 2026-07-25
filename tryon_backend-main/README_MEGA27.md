# MEGA27 — Acciones masivas y hotfix PyAV

ZIP incremental coordinado para backend y backoffice.

## Backend

Copiar sobre `tryon_backend`:

- Normaliza `av==9.0.0` a `av==12.3.0` tanto en dependencias detectadas como en requirements de Custom Nodes copiados.
- Conserva el hotfix de `mediapipe==0.10.21` y las dependencias nativas de MEGA26.
- Agrega cancelación y eliminación múltiple de builds.
- Agrega cancelación y eliminación múltiple de ejecuciones de generación.
- La eliminación omite builds activos y ejecuciones no terminales.

## BackOffice

Copiar sobre `tryon_backoffice`:

- Checkboxes individuales.
- Seleccionar todo.
- Cancelar seleccionadas.
- Eliminar seleccionadas.
- Disponible en Runtime Builder > Builds y Trabajos IA.

## Importante

Para aplicar el hotfix de PyAV al Dockerfile/requirements exportados, reinicia el backend y vuelve a exportar el runtime con Sobrescribir. Después ejecuta un build nuevo.

No requiere migración de base de datos.
