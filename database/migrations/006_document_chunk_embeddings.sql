-- Keep vectors beside their authoritative PostgreSQL chunk and ownership row.
BEGIN;

CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE document_chunks
    ADD COLUMN embedding vector(384);

CREATE INDEX document_chunks_embedding_cosine_idx
    ON document_chunks USING hnsw (embedding vector_cosine_ops)
    WHERE embedding IS NOT NULL;

COMMIT;
