# MegaZIP 2A — Backend Caja y Bolsas

## Aplicar
1. Descomprimir sobre la raíz del Backend.
2. Activar `.venv`.
3. Ejecutar `alembic upgrade head`.
4. Ejecutar:
   `python -m compileall -q app alembic/versions tests`
   `python -m pytest tests/test_finance_cashbox_contract.py -v`
5. Reiniciar el Backend.

## Incluye
- Ciclo de vida de bolsas: nueva, activa, agotada, expirada, reembolsada.
- Primer consumo libera toda la utilidad comercial congelada.
- Reserva de infraestructura restante protegida por bolsa.
- Caja disponible con retiros descontados.
- Caducidad global configurable (1–3650 días), congelada por bolsa.
- Expiración sin generaciones ficticias y liberación económica auditable.
- Tabla/detalle API de bolsas y generaciones asociadas.
- Conciliación/reembolso reutilizando Stripe existente.
- Reembolso automático bloqueado cuando la bolsa ya consumió tokens.
