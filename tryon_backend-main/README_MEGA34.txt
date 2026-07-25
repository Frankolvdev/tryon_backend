MEGA34 - Validación pip check tolerante al falso positivo de decord

Cambios incrementales sobre MEGA33:
- Mantiene `python -m pip check` como validación obligatoria.
- Permite continuar únicamente cuando la única salida de error es exactamente:
  `decord 0.6.0 is not supported on this platform`
- Cualquier otro conflicto o dependencia rota continúa deteniendo el docker build.
- No altera Python 3.11, CUDA 12.8, PyTorch cu128, GEOS, constraints,
  normalización de requirements ni copia local de Custom Nodes.

Después de aplicar el parche, reinicie el backend y genere una exportación nueva.
No reutilice un Dockerfile creado antes de MEGA34.
