-- Add the current upload format and a recoverable private-blob deletion state.
BEGIN;

ALTER TABLE documents
    DROP CONSTRAINT documents_file_format_check;

-- Keep legacy .ppt metadata readable, but the upload API accepts .pptx only.
ALTER TABLE documents
    ADD CONSTRAINT documents_file_format_check
        CHECK (file_format IN ('pdf', 'txt', 'ppt', 'pptx'));

ALTER TABLE documents
    DROP CONSTRAINT documents_status_check;

ALTER TABLE documents
    ADD CONSTRAINT documents_status_check
        CHECK (status IN ('uploaded', 'processing', 'ready', 'failed', 'deleting', 'deleted'));

ALTER TABLE documents
    DROP CONSTRAINT documents_deleted_status_ck;

ALTER TABLE documents
    ADD CONSTRAINT documents_deleted_status_ck
        CHECK ((status IN ('deleting', 'deleted')) = (deleted_at IS NOT NULL));

COMMIT;
