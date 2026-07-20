# Backend 01G-B1 — OAuth model registration and migration

This incremental package completes the persistence foundation introduced in
`backend_01G_A_oauth_foundation.zip`.

## Included changes

- Registers `OAuthAccount` in `app.models`, allowing Alembic to include the
  model metadata.
- Adds the Alembic migration that creates `oauth_accounts`.
- Preserves the existing email/password, JWT, MFA, registration and password
  recovery flows without modifying their routes or services.

## Apply

```powershell
alembic upgrade head
```

## Validate

```powershell
python -m compileall app alembic
```

The next increment will add provider configuration and shared OAuth services;
this package does not expose OAuth routes yet.
