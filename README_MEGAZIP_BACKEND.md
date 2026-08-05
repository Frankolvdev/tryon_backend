# MegaZIP 1 — Backend: bolsas comerciales, cupones y renovaciones

- Los cupones se calculan completamente en el backend. Stripe recibe solo el importe final.
- Cada compra/renovación congela: valor del token, ganancia normal por token, descuento y ganancia final por token.
- El consumo FIFO conserva mezclas de bolsas con condiciones distintas.
- Finanzas separa dinero para proveedor, beneficio al cliente y ganancia de la empresa.
- Al sincronizar un plan modificado, el precio nuevo se agenda sin prorrateo para la siguiente renovación.
- Al archivar un plan, las suscripciones existentes terminan al final del periodo; no renuevan ni reciben tokens futuros.

No requiere migración Alembic nueva.

Validación:
python -m compileall -q app tests
python -m pytest tests/test_commercial_snapshots_and_finance_contract.py -v
