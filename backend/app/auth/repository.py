import os
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row


class DuplicateEmailError(Exception):
    """Raised when the normalized email is already registered."""


class PostgresAuthRepository:
    def __init__(self, database_url: str | None = None) -> None:
        self._database_url = database_url

    def _connect(self) -> psycopg.Connection:
        database_url = self._database_url or os.getenv("DATABASE_URL")
        if not database_url:
            raise RuntimeError("DATABASE_URL is not configured")
        # Neon pooled URLs are supplied through DATABASE_URL in serverless deployments.
        return psycopg.connect(database_url, row_factory=dict_row)

    def create_user(
        self,
        email: str,
        password_hash: str,
        display_name: str,
        timezone_name: str = "UTC",
    ) -> dict:
        try:
            with self._connect() as connection:
                user = connection.execute(
                    """
                    INSERT INTO users (id, email, password_hash, display_name, timezone)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id, email, display_name, timezone, created_at
                    """,
                    (uuid4(), email, password_hash, display_name, timezone_name),
                ).fetchone()
                return user
        except psycopg.errors.UniqueViolation as error:
            raise DuplicateEmailError from error

    def get_user_by_email(self, email: str) -> dict | None:
        with self._connect() as connection:
            return connection.execute(
                """
                SELECT id, email, password_hash, display_name, timezone, created_at
                FROM users WHERE email = %s
                """,
                (email,),
            ).fetchone()

    def create_session(self, user_id: UUID, token_hash: str) -> datetime:
        created_at = datetime.now(timezone.utc)
        expires_at = created_at + timedelta(days=7)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO auth_sessions (id, user_id, token_hash, created_at, expires_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (uuid4(), user_id, token_hash, created_at, expires_at),
            )
        return expires_at

    def get_user_for_session(self, token_hash: str) -> dict | None:
        with self._connect() as connection:
            return connection.execute(
                """
                SELECT users.id, users.email, users.display_name, users.timezone, users.created_at
                FROM auth_sessions
                JOIN users ON users.id = auth_sessions.user_id
                WHERE auth_sessions.token_hash = %s
                  AND auth_sessions.revoked_at IS NULL
                  AND auth_sessions.expires_at > now()
                """,
                (token_hash,),
            ).fetchone()

    def revoke_session(self, token_hash: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE auth_sessions SET revoked_at = now()
                WHERE token_hash = %s AND revoked_at IS NULL
                """,
                (token_hash,),
            )

    def update_profile(
        self,
        user_id: UUID,
        display_name: str | None,
        timezone_name: str | None,
    ) -> dict | None:
        with self._connect() as connection:
            return connection.execute(
                """
                UPDATE users
                SET display_name = COALESCE(%s, display_name),
                    timezone = COALESCE(%s, timezone),
                    updated_at = now()
                WHERE id = %s
                RETURNING id, email, display_name, timezone, created_at
                """,
                (display_name, timezone_name, user_id),
            ).fetchone()
