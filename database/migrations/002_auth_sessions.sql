-- Opaque, revocable browser sessions for the authentication module.
BEGIN;

CREATE TABLE auth_sessions (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    token_hash TEXT NOT NULL UNIQUE
        CHECK (token_hash ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    CONSTRAINT auth_sessions_user_fk
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    CONSTRAINT auth_sessions_id_user_uq UNIQUE (id, user_id),
    CONSTRAINT auth_sessions_expiry_ck CHECK (expires_at > created_at)
);

CREATE INDEX auth_sessions_user_expiry_idx
    ON auth_sessions (user_id, expires_at);

COMMIT;
