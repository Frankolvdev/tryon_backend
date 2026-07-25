# Backend 01G-B2 — OAuth multi-provider configuration

This incremental package prepares the existing integration configuration system
for Google, GitHub, Facebook and Apple OAuth without modifying email/password
login, JWT, MFA, registration or password recovery.

## Changes

- Restores the response schemas required by the existing BackOffice OAuth
  providers endpoint.
- Adds `github_oauth` to `IntegrationProvider`.
- Adds GitHub OAuth to integration default seeding.
- Centralizes provider metadata and database-backed runtime configuration.
- Requires client ID, client secret and redirect URI before a provider is
  reported as configured.
- Keeps secrets out of API responses.

## Apply

Run the existing integration seed action from the BackOffice or API to create
GitHub's integration record on installations that were seeded previously.
No Alembic migration is required because integration provider values are stored
as strings.
