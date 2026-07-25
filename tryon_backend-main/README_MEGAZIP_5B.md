# MegaZIP 5B — Ejecución completa de pipelines en Modal

Este paquete agrega Modal como ejecutor remoto del contrato `tryon.generation-runtime/v1` sin sustituir los motores existentes.

Después de aplicarlo:

1. Regenera el runtime desde Runtime Builder para que el nuevo `modal_app.py` incluya `POST /api/tryon/pipeline`.
2. Vuelve a construir y desplegar el runtime en Modal.
3. Copia la URL pública desplegada en Proveedores de infraestructura > Modal > URL pública del runtime Modal.
4. Activa Modal y selecciona `Modal` en el campo Motor del módulo de generación que quieras ejecutar allí.

El backend conserva Redis, tokens, estados, historial, reembolsos y persistencia. Modal recibe el pipeline completo, ejecuta workflows y bloques Python en el mismo contenedor GPU y devuelve todas las salidas finales configuradas.
