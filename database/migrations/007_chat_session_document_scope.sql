-- Persist the ready documents selected for each conversation.
BEGIN;

CREATE TABLE chat_session_documents (
    user_id UUID NOT NULL,
    session_id UUID NOT NULL,
    document_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (session_id, document_id),
    CONSTRAINT chat_session_documents_session_user_fk
        FOREIGN KEY (session_id, user_id)
        REFERENCES chat_sessions (id, user_id) ON DELETE CASCADE,
    CONSTRAINT chat_session_documents_document_user_fk
        FOREIGN KEY (document_id, user_id)
        REFERENCES documents (id, user_id) ON DELETE CASCADE
);

CREATE INDEX chat_session_documents_user_document_idx
    ON chat_session_documents (user_id, document_id);

COMMIT;
