# FIX Backend — Reset de actividad de pruebas actualizado

BASE
tryon_backend-main - 2026-08-07T161134.916.zip

OBJETIVO
Actualizar la función existente "BORRAR ACTIVIDAD DE PRUEBAS" para que limpie
también todas las estructuras financieras agregadas recientemente, sin borrar
usuarios ni configuración del sistema.

SE BORRA / REINICIA
- Generaciones y ejecuciones.
- TryOn jobs legacy.
- Archivos de uploads/resultados/galería de prueba.
- Gallery items.
- Token balances -> 0.
- Token transactions.
- Token value lots / bolsas.
- Token consumption allocations.
- Compras de tokens.
- Billing payments/invoices/events/customers.
- Suscripciones locales.
- Registros financieros por generación.
- Retiros de utilidad.
- Transferencias de infraestructura.
- Asignaciones FIFO de transferencias a bolsas.
- Registros de dinero que quedó dentro de proveedores al vencer.
- Fondos promocionales.
- Grants de tokens promocionales.
- Devoluciones de créditos promocionales.
- Gastos de la caja operativa.
- Jobs externos/background.
- Legal acceptances asociadas a la actividad comercial de prueba.
- Storage de actividad de prueba.

COBROS PENDIENTES / RESULTADOS BLOQUEADOS
No tienen una tabla financiera independiente. Su estado vive dentro de las
ejecuciones/snapshots existentes, por lo que desaparecen correctamente al
borrar generation_module_executions y generation_financial_records.

SE CONSERVA
- Usuarios.
- Email/password/verificación/roles.
- Avatar del usuario.
- Configuración del sistema.
- Pricing rules.
- Valor base de token.
- Extra por gastos del negocio.
- Paquetes.
- Planes.
- Cupones.
- Precios de GPU.
- Configuración de proveedores.
- Módulos de generación.
- Configuración promocional (switches/settings), pero no sus fondos/grants de prueba.

PROTECCIÓN NUEVA DE AVATARES
El reset anterior borraba todos los storage_files. Eso podía borrar también
el archivo de avatar aunque el usuario sobreviviera. Ahora los avatar_file_id
de usuarios se excluyen expresamente del borrado.

PREVIEW
Ahora incluye contadores explícitos para:
- promotional_credit_returns
- promotional_token_grants
- promotional_credit_funds
- operational_expenses
- infrastructure funding/release tables (ya existentes)
- users_preserved
- account_files_preserved

BLINDAJE
No hay migración.
No se modifican fórmulas, FIFO, snapshots, Stripe, Modal, RunPod ni Beam.

VALIDACIÓN REALIZADA
54 passed en contratos relacionados, incluidos:
- reset financiero V4
- caja operativa
- snapshots/descuentos operativos
- créditos promocionales
- infraestructura FIFO
- vencimientos
- auto-desbloqueo
- cobros pendientes

APLICACIÓN
Extraer directamente sobre la raíz del backend.

VALIDACIÓN
python -m compileall -q app tests
python -m pytest -q tests/test_generation_data_reset_financial_v4_contract.py

GIT
git add .
git commit -m "fix: reset all test financial activity while preserving users"
git push
