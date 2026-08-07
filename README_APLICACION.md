# MegaZIP 1A — Backend — Pérdidas pendientes + auto-desbloqueo

BASE:
tryon_backend-main - 2026-08-07T114606.749.zip

OBJETIVO:
Agregar la vista financiera de cobros/pérdidas pendientes y el auto-desbloqueo
posterior a créditos comerciales pagados, sin crear otra fórmula de facturación.

GARANTÍAS DE DISEÑO:
- No modifica pricing_service ni la fórmula de tokens.
- No modifica FIFO de tokens ni snapshots.
- No modifica token_value_ledger_service.
- No modifica generation_module_billing_service.
- No modifica Modal, RunPod, Beam, Stripe checkout ni proveedores.
- No modifica el botón manual de desbloqueo.
- No requiere migración de base de datos.
- La compra se acredita y COMMITTEA antes del auto-desbloqueo.
- Un fallo del auto-desbloqueo no revierte la compra.
- Las deudas se intentan de la más antigua a la más reciente.
- Cada generación se paga completa o no se toca.
- El auto-desbloqueo reutiliza exactamente settle_pending_billing().
- Solo compra Stripe acreditada y renovación pagada disparan el auto-desbloqueo.
  Signup, admin grants y futuros créditos promocionales NO lo disparan.

PÉRDIDAS PENDIENTES:
- Infraestructura pendiente: costo real ya incurrido y todavía no respaldado/cobrado.
- Ganancia pendiente: estimación potencial; puede cambiar según las bolsas/descuentos
  que finalmente paguen el ajuste.
- No altera la caja verde ni ninguna cuenta existente.

VALIDACIÓN:
python -m compileall -q app tests alembic/versions

Contratos relevantes ejecutados:
57 passed
1 contrato histórico preexistente falló también en el ZIP base:
tests/test_finance_bag_historical_compatibility_contract.py
No fue modificado ni maquillado por este MegaZIP.

No hay migración Alembic en este MegaZIP.
