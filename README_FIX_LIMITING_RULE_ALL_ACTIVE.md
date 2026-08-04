# FIX — Regla de mayor riesgo entre todas las reglas activas

Corrige el cálculo financiero para que ninguna regla de pricing activa quede fuera por no tener módulo vinculado o porque su módulo esté inactivo.

La regla de mayor riesgo se selecciona exclusivamente por el menor `desired_profit_usd` entre todas las reglas activas. La relación con el módulo se conserva solo como información diagnóstica.

Esto evita que una regla como `Nude` con USD 0.50 sea ignorada y que se muestre erróneamente `Face Swap` con USD 1.00.
