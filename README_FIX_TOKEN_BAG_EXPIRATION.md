# Fix de vencimiento de bolsas

- Evita duplicar la ganancia comercial cuando vence una bolsa nunca utilizada.
- La liberación por vencimiento contiene exclusivamente la reserva de IA de los tokens vencidos.
- La ganancia comercial se registra en su campo independiente.
- Añade una simulación administrativa, únicamente fuera de producción y desactivada por defecto.

## Activar simulación
En `.env`:

```env
TEST_FORCE_TOKEN_BAG_EXPIRATION=true
```

Reiniciar el backend y usar:

`POST /api/v1/admin/finances/token-bags/{bag_id}/simulate-expiration`

Body:

```json
{"confirm": true}
```

Desactivar al terminar:

```env
TEST_FORCE_TOKEN_BAG_EXPIRATION=false
```
