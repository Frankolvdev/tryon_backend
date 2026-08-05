# Fix reglas de cupones

- Vigencia controlada únicamente por fechas.
- Máximo de usos global y por usuario.
- Conteo del uso solo cuando Stripe confirma el pago.
- Usuarios elegibles por ID interno seleccionado desde BackOffice.
- Compra mínima eliminada del contrato de creación/edición.

No requiere migración Alembic: los límites por usuario y usuarios permitidos se guardan en metadata_json; redemption_count sigue siendo el contador global.
