# FIX Backend — Regla de mayor riesgo por menor Ganancia deseada

Corrige el selector de la regla limitante. Antes se elegía la menor ganancia por token; ahora se elige exclusivamente la regla activa aplicada con menor `desired_profit_usd`.

Los tokens estimados solo se usan después para escalar la ganancia de esa regla en planes y paquetes.
