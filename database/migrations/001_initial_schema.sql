-- Initial relational schema for the MemoCard AI MVP.
-- UUID values are supplied by the application to avoid PostgreSQL extension dependencies.
BEGIN;

CREATE TABLE users (
    id UUID PRIMARY KEY,
    email TEXT NOT NULL CHECK (length(btrim(email)) > 0),
    password_hash TEXT NOT NULL CHECK (length(btrim(password_hash)) > 0),
    display_name TEXT NOT NULL CHECK (length(btrim(display_name)) > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Enforce case-insensitive uniqueness without requiring the citext extension.
CREATE UNIQUE INDEX users_email_case_insensitive_uq ON users (lower(email));

CREATE TABLE documents (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    original_filename TEXT NOT NULL CHECK (length(btrim(original_filename)) > 0),
    file_format TEXT NOT NULL CHECK (file_format IN ('pdf', 'txt', 'ppt')),
    storage_key TEXT NOT NULL CHECK (length(btrim(storage_key)) > 0),
    size_bytes BIGINT NOT NULL CHECK (size_bytes >= 0),
    status TEXT NOT NULL DEFAULT 'uploaded'
        CHECK (status IN ('uploaded', 'processing', 'ready', 'failed', 'deleted')),
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ,
    CONSTRAINT documents_user_fk
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE RESTRICT,
    CONSTRAINT documents_id_user_uq UNIQUE (id, user_id),
    CONSTRAINT documents_deleted_status_ck
        CHECK ((status = 'deleted') = (deleted_at IS NOT NULL))
);

CREATE INDEX documents_user_status_created_idx
    ON documents (user_id, status, created_at DESC)
    WHERE deleted_at IS NULL;

CREATE TABLE document_chunks (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    document_id UUID NOT NULL,
    chunk_index INTEGER NOT NULL CHECK (chunk_index >= 0),
    content TEXT NOT NULL CHECK (length(btrim(content)) > 0),
    page_number INTEGER CHECK (page_number IS NULL OR page_number > 0),
    slide_number INTEGER CHECK (slide_number IS NULL OR slide_number > 0),
    content_hash TEXT NOT NULL CHECK (length(btrim(content_hash)) > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT document_chunks_document_user_fk
        FOREIGN KEY (document_id, user_id)
        REFERENCES documents (id, user_id) ON DELETE CASCADE,
    CONSTRAINT document_chunks_document_order_uq UNIQUE (document_id, chunk_index),
    CONSTRAINT document_chunks_id_user_uq UNIQUE (id, user_id),
    CONSTRAINT document_chunks_id_document_user_uq UNIQUE (id, document_id, user_id),
    CONSTRAINT document_chunks_single_locator_ck
        CHECK (page_number IS NULL OR slide_number IS NULL)
);

CREATE TABLE chat_sessions (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    title TEXT CHECK (title IS NULL OR length(title) <= 200),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chat_sessions_user_fk
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE RESTRICT,
    CONSTRAINT chat_sessions_id_user_uq UNIQUE (id, user_id)
);

CREATE INDEX chat_sessions_user_updated_idx
    ON chat_sessions (user_id, updated_at DESC);

CREATE TABLE chat_messages (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    session_id UUID NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL CHECK (length(btrim(content)) > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chat_messages_session_user_fk
        FOREIGN KEY (session_id, user_id)
        REFERENCES chat_sessions (id, user_id) ON DELETE CASCADE,
    CONSTRAINT chat_messages_id_user_uq UNIQUE (id, user_id)
);

CREATE INDEX chat_messages_session_created_idx
    ON chat_messages (session_id, created_at, id);

CREATE TABLE message_citations (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    message_id UUID NOT NULL,
    document_chunk_id UUID NOT NULL,
    citation_rank SMALLINT NOT NULL CHECK (citation_rank > 0),
    excerpt TEXT NOT NULL CHECK (length(btrim(excerpt)) > 0),
    page_number INTEGER CHECK (page_number IS NULL OR page_number > 0),
    slide_number INTEGER CHECK (slide_number IS NULL OR slide_number > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT message_citations_message_user_fk
        FOREIGN KEY (message_id, user_id)
        REFERENCES chat_messages (id, user_id) ON DELETE CASCADE,
    CONSTRAINT message_citations_chunk_user_fk
        FOREIGN KEY (document_chunk_id, user_id)
        REFERENCES document_chunks (id, user_id) ON DELETE RESTRICT,
    CONSTRAINT message_citations_message_rank_uq UNIQUE (message_id, citation_rank),
    CONSTRAINT message_citations_single_locator_ck
        CHECK (page_number IS NULL OR slide_number IS NULL)
);

CREATE INDEX message_citations_chunk_idx
    ON message_citations (document_chunk_id);

CREATE TABLE flashcards (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    source_message_id UUID,
    question TEXT NOT NULL CHECK (length(btrim(question)) > 0),
    answer TEXT NOT NULL CHECK (length(btrim(answer)) > 0),
    repetition_count INTEGER NOT NULL DEFAULT 0 CHECK (repetition_count >= 0),
    ease_factor NUMERIC(6, 3) NOT NULL DEFAULT 2.500 CHECK (ease_factor >= 1.300),
    interval_days INTEGER NOT NULL DEFAULT 0 CHECK (interval_days >= 0),
    last_reviewed_at TIMESTAMPTZ,
    next_review_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT flashcards_user_fk
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE RESTRICT,
    CONSTRAINT flashcards_source_message_user_fk
        FOREIGN KEY (source_message_id, user_id)
        REFERENCES chat_messages (id, user_id) ON DELETE RESTRICT,
    CONSTRAINT flashcards_id_user_uq UNIQUE (id, user_id)
);

CREATE INDEX flashcards_due_idx
    ON flashcards (user_id, next_review_at);

CREATE TABLE flashcard_sources (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    flashcard_id UUID NOT NULL,
    document_id UUID NOT NULL,
    document_chunk_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT flashcard_sources_card_user_fk
        FOREIGN KEY (flashcard_id, user_id)
        REFERENCES flashcards (id, user_id) ON DELETE CASCADE,
    CONSTRAINT flashcard_sources_document_user_fk
        FOREIGN KEY (document_id, user_id)
        REFERENCES documents (id, user_id) ON DELETE RESTRICT,
    CONSTRAINT flashcard_sources_chunk_document_user_fk
        FOREIGN KEY (document_chunk_id, document_id, user_id)
        REFERENCES document_chunks (id, document_id, user_id) ON DELETE RESTRICT
);

CREATE UNIQUE INDEX flashcard_sources_document_uq
    ON flashcard_sources (flashcard_id, document_id)
    WHERE document_chunk_id IS NULL;

CREATE UNIQUE INDEX flashcard_sources_chunk_uq
    ON flashcard_sources (flashcard_id, document_chunk_id)
    WHERE document_chunk_id IS NOT NULL;

CREATE INDEX flashcard_sources_document_idx
    ON flashcard_sources (document_id);

CREATE TABLE flashcard_reviews (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    flashcard_id UUID NOT NULL,
    quality SMALLINT NOT NULL CHECK (quality BETWEEN 0 AND 5),
    reviewed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    repetition_count_before INTEGER NOT NULL CHECK (repetition_count_before >= 0),
    repetition_count_after INTEGER NOT NULL CHECK (repetition_count_after >= 0),
    interval_days_before INTEGER NOT NULL CHECK (interval_days_before >= 0),
    interval_days_after INTEGER NOT NULL CHECK (interval_days_after >= 0),
    ease_factor_before NUMERIC(6, 3) NOT NULL CHECK (ease_factor_before >= 1.300),
    ease_factor_after NUMERIC(6, 3) NOT NULL CHECK (ease_factor_after >= 1.300),
    next_review_at_after TIMESTAMPTZ NOT NULL,
    CONSTRAINT flashcard_reviews_card_user_fk
        FOREIGN KEY (flashcard_id, user_id)
        REFERENCES flashcards (id, user_id) ON DELETE CASCADE
);

CREATE INDEX flashcard_reviews_card_time_idx
    ON flashcard_reviews (flashcard_id, reviewed_at DESC);

-- updated_at is maintained by application writes; no database trigger is required.
COMMIT;
