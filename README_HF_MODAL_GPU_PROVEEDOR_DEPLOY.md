# Hotfix Modal GPU de despliegue

Corrige dos rutas de despliegue que podían publicar el runtime con L40S aunque el proveedor Modal estuviera configurado con A100-80GB.

Cambios:
- La GPU guardada en Proveedores de infraestructura > Modal es la fuente principal del deploy.
- El flujo de publicación antiguo ahora también envía TRYON_MODAL_GPU y el resto de variables de ejecución.
- Los logs de deploy indican explícitamente la GPU seleccionada.

Después de aplicar:
1. Reinicia el backend.
2. Confirma A100-80GB en Proveedores de infraestructura > Modal y guarda.
3. Vuelve a desplegar/publicar el build en Modal.
4. Una configuración guardada no cambia un deployment ya existente: hay que ejecutar modal deploy nuevamente.
