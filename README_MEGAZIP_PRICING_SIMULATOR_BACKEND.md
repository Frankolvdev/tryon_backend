# MegaZIP Backend — Simulador de precios y ganancias

Agrega un endpoint administrativo de solo lectura:

`POST /api/v1/admin/pricing-simulator`

Usa la misma fórmula del motor real, el módulo seleccionado, su regla activa, GPU, costo por segundo, historial ponderado, scaledown y margen técnico. No guarda cambios ni crea movimientos financieros.

Permite comparar escenarios de descuento y buscar combinaciones cercanas a una ganancia objetivo dentro de un rango de tokens.
