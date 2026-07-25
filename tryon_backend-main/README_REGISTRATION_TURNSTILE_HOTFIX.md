# Hotfix de registro: `turnstile_token`

## Problema corregido

El esquema `UserCreate` contiene `turnstile_token`, pero el modelo SQLAlchemy
`User` no tiene una columna con ese nombre. `create_user()` estaba pasando ese
campo a `user_repository.create()`, provocando:

```text
TypeError: 'turnstile_token' is an invalid keyword argument for User
```

## Aplicación

Descomprime este ZIP directamente sobre la raíz de `tryon_backend` y ejecuta:

```powershell
python scripts/apply_registration_turnstile_hotfix.py
```

El script:

- modifica solamente `app/services/user_service.py`;
- agrega `user_dict.pop("turnstile_token", None)`;
- conserva la validación anti-bot;
- no modifica el modelo ni la base de datos;
- crea un respaldo antes de cambiar el archivo;
- no vuelve a aplicar el cambio si ya existe;
- se detiene sin modificar nada si el archivo no coincide con la versión esperada.

## Verificación

```powershell
python -m compileall app
uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

Después registra una cuenta nueva desde:

```text
http://localhost:3003/register
```

## Limpieza opcional

Cuando confirmes que el registro funciona:

```powershell
Remove-Item app/services/user_service.py.before_turnstile_hotfix -ErrorAction SilentlyContinue
```
