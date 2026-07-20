# Backend 01G-C1 — Google OAuth provider client

This incremental package adds the Google OpenID Connect provider implementation.

## Included

- Google authorization URL generation with state and optional PKCE.
- Authorization-code exchange through Google's token endpoint.
- Normalized user profile retrieval through Google's OIDC userinfo endpoint.
- Runtime registry factory using credentials already stored in integrations.
- Controlled application errors without exposing client secrets or provider responses.

## Not included yet

This package intentionally does not expose public OAuth routes or create/login users. Those pieces are added in the next incremental package so the existing email/password authentication remains isolated.

## Validation

```powershell
python -m compileall app alembic
```
