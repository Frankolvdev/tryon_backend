# Fix: descuentos únicamente sobre Ganancia deseada (USD)

- La menor Ganancia deseada (USD) entre reglas activas es la ganancia segura global.
- Esa ganancia representa 100% del presupuesto de descuentos.
- No se leen ni modifican duración, GPU, scaledown, margen técnico, infraestructura o telemetría.
- Planes y paquetes aceptan de 0% a 100% sobre la ganancia segura.
- Cupones son únicamente porcentuales.
- Paquete + cupón no puede superar 100% combinado.
- El backend informa la pérdida potencial en USD cuando se intenta exceder el límite.
- Se elimina el PATCH de configuración financiera manual; Pricing queda como diagnóstico.
