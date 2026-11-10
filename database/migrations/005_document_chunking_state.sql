-- Distinguish PostgreSQL text extraction from completed vector indexing.
BEGIN;

ALTER TABLE documents
    DROP CONSTRAINT documents_status_check;

ALTER TABLE documents
    ADD CONSTRAINT documents_status_check
        CHECK (status IN ('uploaded', 'processing', 'chunked', 'ready', 'failed', 'deleting', 'deleted'));

COMMIT;
