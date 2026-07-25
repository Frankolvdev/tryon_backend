# Backend 01G-C2 — Google OAuth flow

Adds the complete backend browser flow for Google OAuth without replacing email/password authentication.

## Endpoints

- `POST /api/v1/oauth/google/start`
- `GET /api/v1/oauth/google/callback`
- `POST /api/v1/oauth/exchange`

The callback redirects to the approved AppWeb URL with a short-lived, single-use code. AppWeb exchanges that code for the normal access and refresh token pair. Tokens are never placed in the browser URL.

## Requirements

- Redis must be running.
- `FRONTEND_URL` must match the AppWeb origin, for example `http://localhost:3003`.
- Google OAuth integration must contain the client ID and secret and be enabled.
- The Google Console callback URL must be the backend callback URL, for example `http://127.0.0.1:8001/api/v1/oauth/google/callback`.
