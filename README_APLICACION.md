# MegaZIP — Backend — Simulador + Administración de usuarios + limpieza de Configuración

BASE EXACTA
tryon_backend-main - 2026-08-07T163457.497.zip

ALCANCE

1. SIMULADOR DE GANANCIAS
- Se conserva la fórmula y comportamiento existente.
- Ya contemplaba correctamente el componente operativo; se blinda mediante contratos.
- Los tokens promocionales NO se mezclan con el simulador comercial:
  cliente paga 0, ganancia 0 y operación 0.
- Se corrige un bug preexistente en recomendaciones: una recomendación podía
  devolver el token_value de la última iteración evaluada en vez del
  token_value de la recomendación seleccionada.
- No cambia el cálculo de tokens, descuentos, FIFO ni infraestructura.

2. ADMINISTRACIÓN DE USUARIO / ALMACENAMIENTO
- Nuevo listado admin de almacenamiento por usuario:
  GET /api/admin/users/{user_id}/storage-files
- Filtra inputs, results, library u otros.
- Conserva el proveedor original de cada StorageFile.
- Nueva eliminación segura de una generación:
  DELETE /api/admin/users/{user_id}/generations/{execution_id}/storage
- Elimina resultados físicos y gallery rows de esa generación.
- NO elimina inputs automáticamente.
- NO elimina GenerationFinancialRecord ni TokenConsumptionAllocation.
  El historial financiero permanece auditable.
- Solo permite eliminar generaciones en estado terminal:
  completed / failed / cancelled.
- Genera AuditLog administrativo.

3. CONFIGURACIÓN
Se elimina del seed y, mediante migración, de system_settings únicamente
configuración sin consumidor real en el código actual:
- app_environment
- max_login_attempts
- password_min_length
- active_payment_provider
- monthly_tokens_reset_enabled
- dynamic_pricing_enabled
- default_margin_percent
- scheduler_timezone
- analytics_enabled
- log_retention_days
- commercial_currency

USD queda fijo como moneda comercial del producto. La API conserva el campo
currency por compatibilidad, pero el backend no necesita una setting para ello.

SE CONSERVAN, ENTRE OTRAS
- precios/token y gasto operativo
- execution billing policy
- storage
- registro/login
- JWT
- billing/subscriptions
- maintenance
- scheduler_enabled
- módulos IA
- RunPod/provider settings
- créditos promocionales/free signup
- frontend URL
- minimum token purchase (se conserva por compatibilidad pública)

MIGRACIÓN OBLIGATORIA
alembic upgrade head

HEAD ESPERADO
05d_unused_settings (head)

VALIDACIÓN REALIZADA
- python -m compileall: OK
- alembic heads: 05d_unused_settings (head)
- 94 contratos acumulados relacionados: PASSED

NO MODIFICA
- AppWeb
- Stripe
- Modal / RunPod / Beam
- generación runtime
- FIFO
- snapshots históricos
- cajas financieras
- auto-desbloqueo
- vencimientos
- fórmulas de precio base

GIT
git add .
git commit -m "feat: upgrade simulator user admin and active settings"
git push
