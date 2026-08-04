# Reinicio temporal de datos de generaciones

Corrige la categoría `integrations` de Configuración y agrega endpoints administrativos para previsualizar y ejecutar un reinicio seguro de datos de generaciones.

## Conserva
Usuarios, saldos no relacionados, módulos, formularios, pricing, planes, paquetes, cupones, suscripciones, proveedores, runtimes y configuración.

## Elimina
Ejecuciones dinámicas, TryOn legacy, registros financieros, asignaciones contables, trabajos externos TryOn, galería vinculada y archivos de entrada/resultado detectados.

## Seguridad temporal
- Rechaza el reinicio si existen trabajos activos.
- Exige escribir exactamente `BORRAR GENERACIONES`.
- Restaura tokens trazables mediante las asignaciones del libro contable.
- Registra auditoría administrativa.

No requiere Alembic.
