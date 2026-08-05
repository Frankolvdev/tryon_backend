# MegaZIP Backend — precisión financiera por generación

Corrige exclusivamente el registro financiero de generaciones nuevas:

- Agrupa asignaciones repetidas de la misma bolsa de tokens.
- `applied_profit_usd` refleja la ganancia después del beneficio comercial.
- Mantiene `profit_rounding_surplus_usd` separado.
- La ganancia total de la empresa suma ganancia después de beneficios + redondeo.
- El costo de infraestructura permanece intacto.

No requiere migración Alembic.

```powershell
python -m compileall -q app tests
python -m pytest tests/test_finance_accuracy_contract.py -v
```
