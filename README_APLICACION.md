# FIX Backend — Retiro de tokens gratis + políticas legales V1.2

BASE
tryon_backend-main - 2026-08-07T170316.291.zip

CAMBIO FUNCIONAL
- Nuevo endpoint POST /api/admin/finances/promotional-credits/revoke.
- Solo puede retirar tokens de bolsas promotional_credit que todavía estén sin gastar.
- Nunca toca compras, planes, cupones ni saldo comercial.
- Si el retiro cruza varias bolsas promocionales, se procesa FIFO.
- Cada token retirado devuelve su respaldo al PromotionalCreditFund exacto que lo financió.
- Si no puede devolverse el respaldo completo, toda la operación falla.
- Se descuenta el wallet del usuario y se registra TokenTransaction de débito.
- Se registra PromotionalCreditReturn reason=admin_revoke.
- Se genera AuditLog administrativo.

POLÍTICAS LEGALES
- Defaults profesionales pasan de 1.1 a 1.2.
- Se explican tokens/créditos promocionales, valor monetario cero, retiro administrativo de no usados, vencimiento y retorno interno al fondo.
- Privacidad contempla registro de asignaciones/retiros promocionales.
- Reembolsos aclara que créditos gratuitos no originan reembolso monetario.
- Caducidad aclara el retorno del respaldo promocional.
- Solo se actualizan automáticamente defaults exactos 1.1/legacy.
- Políticas redactadas manualmente por el administrador NO se sobrescriben.

IMPORTANTE
Los textos son una base administrativa preventiva, no sustituyen revisión jurídica profesional según países de lanzamiento.

BLINDAJE
- Sin migración Alembic.
- No se modifica cálculo de tokens.
- No se modifica FIFO de generaciones.
- No se modifica Caja comercial, utilidad, operación, vencimientos, Stripe ni proveedores.
- El endpoint genérico antiguo se conserva internamente para no romper contratos existentes, pero deja de estar expuesto por este control del BackOffice.

VALIDACIÓN
19 pruebas relacionadas: PASSED
python -m compileall: OK

GIT
git add .
git commit -m "fix: safely revoke promotional tokens and update legal defaults"
git push
