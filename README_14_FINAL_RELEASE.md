# 14 · Cierre y validación final del Backend

Este incremento añade una comprobación de entrega sin modificar endpoints, modelos, migraciones ni arquitectura existente.

## Ejecutar desde la raíz del backend

```powershell
python app/scripts/release_check.py
```

La validación revisa la estructura esencial y compila sintácticamente `app/` y `alembic/`. Después, con PostgreSQL y Redis disponibles, ejecuta las migraciones y las pruebas del proyecto según tu entorno.
