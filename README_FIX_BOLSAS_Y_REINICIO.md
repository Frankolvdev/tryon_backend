# FIX Backend — detalle económico de bolsas y reinicio integral

## Incluye
- Total disponible por bolsa = ganancia base liberada + extras realizados + liberación por caducidad.
- Snapshot ampliado: descuento, cupón, plan/paquete, versión y origen del snapshot.
- Reinicio integral de actividad comercial y generaciones.
- Limpieza física multi-proveedor de todos los archivos de prueba.
- Eliminación local de bolsas, tokens, pagos, suscripciones, caja, galería y aceptaciones de compra.
- Cancelación opcional de suscripciones Stripe.
- Reembolso opcional de pagos Stripe. Stripe conserva su historial y no permite borrarlo.

No requiere migración Alembic.
