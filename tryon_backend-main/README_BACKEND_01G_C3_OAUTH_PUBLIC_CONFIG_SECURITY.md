# Backend 01G-C3 — OAuth public configuration and closure

Final backend increment for the first Google OAuth integration.

## Added

- `GET /api/v1/oauth/providers`
- Public provider availability response without credentials, secrets, redirect URIs, or authorization URLs.
- Clear distinction between `enabled`, `configured`, and `available`.
- Stable provider names for AppWeb: `google`, `github`, `facebook`, and `apple`.

## Google configuration

The `google_oauth` integration must contain:

- `api_key`: Google OAuth client ID.
- `api_secret`: Google OAuth client secret.
- `config_json.redirect_uri`: the callback URL registered in Google Cloud.
- `is_enabled`: `true`.

For local development, use:

```text
http://127.0.0.1:8001/api/v1/oauth/google/callback
```

The backend environment must point to the AppWeb origin:

```env
FRONTEND_URL=http://localhost:3003
```

## Verification

```powershell
python -m compileall app alembic
alembic upgrade head
```

No database migration is required by this increment.
