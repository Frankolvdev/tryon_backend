# Refinamiento de Pagos y políticas legales — Backend

## Incluye
- Clasificación `processed` / `attempts` sin modificar registros históricos.
- Campos claros de precio original, descuento, cupón, porcentaje, origen y total pagado.
- Conciliación solo cuando existe PaymentIntent.
- Retiro del endpoint administrativo de reembolso desde la vista Pagos; los reembolsos continúan en Caja y Bolsas.
- Textos legales profesionales v1.1. Solo actualiza automáticamente los textos cortos originales exactos; nunca reemplaza documentos editados por el administrador.

## Aplicar
Copiar respetando rutas sobre el Backend actualizado.

```powershell
cd "F:\PROYECTOS PERSONALES\TRYON\backend"
.\.venv\Scripts\Activate.ps1
python -m compileall -q app
# Reiniciar completamente el Backend
```

No requiere migración Alembic.
