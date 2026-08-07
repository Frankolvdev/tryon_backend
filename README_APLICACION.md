# FIX Backend — Política promocionales y deudas V1.3

BASE
tryon_backend-main - 2026-08-07T171500.985.zip

ÚNICO CAMBIO
Se actualizan los Términos y Condiciones predeterminados para dejar explícito que, salvo que la plataforma habilite expresamente esa posibilidad, los créditos promocionales no se aplican al pago, conciliación o desbloqueo de generaciones, saldos o adeudos originados antes de su otorgamiento. Su uso ordinario es para nuevas operaciones posteriores a la acreditación.

VERSIÓN LEGAL
1.2 -> 1.3

PROTECCIÓN
- Solo promueve automáticamente el Término V1.2 si coincide exactamente con el default oficial anterior.
- Si el administrador modificó manualmente el texto, NO se sobrescribe.
- No se modifica ninguna otra política.
- No se modifica motor financiero, tokens, auto-desbloqueo, caja promocional, BackOffice ni AppWeb.
- Sin migración Alembic.

VALIDACIÓN
- legal_document_service.py compila correctamente con py_compile.
- La suite global no pudo recolectarse en el entorno aislado porque el proyecto exige SECRET_KEY; el fallo ocurre durante carga de Settings, antes de ejecutar tests, y no está relacionado con este cambio.

GIT
git add .
git commit -m "legal: clarify promotional credits cannot pay prior debts"
git push
