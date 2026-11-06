# Authentication API

This backend module provides cookie-based registration, login, logout, and profile access. The frontend and API are expected to share one origin initially; a separate frontend origin will require an explicit CORS and cookie policy before deployment.

## Routes

| Method | Path | Behavior |
|---|---|---|
| POST | `/api/auth/register` | Create an account and start a session. |
| POST | `/api/auth/login` | Verify credentials and start a session. |
| POST | `/api/auth/logout` | Revoke the current session and clear its cookie. |
| GET | `/api/auth/me` | Return the authenticated user's public profile. |
| PATCH | `/api/auth/me` | Update the authenticated user's display name. |

The browser cookie is HttpOnly, SameSite=Lax, secure by default, and valid for seven days. Set `APP_ENV=development` only for local HTTP testing. The opaque cookie token is never stored in PostgreSQL; `auth_sessions` stores its SHA-256 digest, owner, expiry, and revocation time.

## Database and environment

Apply `database/migrations/001_initial_schema.sql` followed by `database/migrations/002_auth_sessions.sql` to a PostgreSQL database before using these routes. The API reads `DATABASE_URL`; for Neon serverless deployments, provide the pooled connection URL through the deployment's secret settings. This project does not connect to or migrate Neon automatically.

## Local checks

Create a virtual environment, install `requirements.txt`, then run:

```powershell
python -m unittest discover -s tests -v
```

The current tests exercise route handlers with a fake repository. They do not verify SQL against a live PostgreSQL server.
