# Backend — conciliación pendiente blindada

Reemplaza únicamente `app/services/generation_module_runtime_service.py`.

El cambio se ejecuta solo cuando una generación completada no puede cubrir su costo final con las bolsas financiadas. Crea o actualiza el registro financiero pendiente usando el mismo execution_id. No modifica FIFO, descuentos, Stripe ni proveedores.
