import os
from uuid import UUID

import psycopg
from psycopg.rows import dict_row


class PostgresDocumentRepository:
    def __init__(self, database_url: str | None = None) -> None:
        self._database_url = database_url

    def _connect(self) -> psycopg.Connection:
        database_url = self._database_url or os.getenv("DATABASE_URL")
        if not database_url:
            raise RuntimeError("DATABASE_URL is not configured")
        return psycopg.connect(database_url, row_factory=dict_row)

    def create_document(
        self,
        document_id: UUID,
        user_id: UUID,
        filename: str,
        file_format: str,
        storage_key: str,
        size_bytes: int,
    ) -> dict:
        with self._connect() as connection:
            return connection.execute(
                """
                INSERT INTO documents (
                    id, user_id, original_filename, file_format, storage_key, size_bytes
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, original_filename, file_format, size_bytes,
                          status, error_message, created_at, deleted_at
                """,
                (document_id, user_id, filename, file_format, storage_key, size_bytes),
            ).fetchone()

    def list_documents(self, user_id: UUID) -> list[dict]:
        with self._connect() as connection:
            return connection.execute(
                """
                SELECT id, original_filename, file_format, size_bytes,
                       status, error_message, created_at, deleted_at
                FROM documents
                WHERE user_id = %s AND status <> 'deleted'
                ORDER BY created_at DESC, id DESC
                """,
                (user_id,),
            ).fetchall()

    def get_document(self, user_id: UUID, document_id: UUID) -> dict | None:
        with self._connect() as connection:
            return connection.execute(
                """
                SELECT id, user_id, original_filename, file_format, storage_key,
                       size_bytes, status, error_message, created_at, deleted_at
                FROM documents
                WHERE id = %s AND user_id = %s
                """,
                (document_id, user_id),
            ).fetchone()

    def begin_processing(self, user_id: UUID, document_id: UUID) -> tuple[dict, bool] | None:
        """Claim a new/retryable processing attempt without allowing two workers to race."""
        with self._connect() as connection:
            with connection.transaction():
                document = connection.execute(
                    """
                    SELECT id, user_id, original_filename, file_format, storage_key,
                           size_bytes, status, error_message, created_at, deleted_at,
                           updated_at
                    FROM documents
                    WHERE id = %s AND user_id = %s
                    FOR UPDATE
                    """,
                    (document_id, user_id),
                ).fetchone()
                if document is None or document["status"] in {"deleting", "deleted"}:
                    return None

                stale_processing = document["status"] == "processing" and connection.execute(
                    "SELECT %s < now() - interval '15 minutes' AS is_stale",
                    (document["updated_at"],),
                ).fetchone()["is_stale"]
                can_claim = document["status"] in {"uploaded", "chunked", "failed"} or stale_processing
                if not can_claim:
                    return document, False

                claimed_document = connection.execute(
                    """
                    UPDATE documents
                    SET status = 'processing', error_message = NULL, updated_at = now()
                    WHERE id = %s AND user_id = %s AND deleted_at IS NULL
                    RETURNING id, user_id, original_filename, file_format, storage_key,
                              size_bytes, status, error_message, created_at, deleted_at,
                              updated_at
                    """,
                    (document_id, user_id),
                ).fetchone()
                return claimed_document, True

    def replace_chunks_and_mark_chunked(self, user_id: UUID, document_id: UUID, chunks) -> bool:
        """Atomically replace retryable pre-index chunks and complete extraction."""
        with self._connect() as connection:
            with connection.transaction():
                document = connection.execute(
                    """
                    SELECT status
                    FROM documents
                    WHERE id = %s AND user_id = %s
                    FOR UPDATE
                    """,
                    (document_id, user_id),
                ).fetchone()
                if document is None or document["status"] != "processing":
                    return False

                connection.execute(
                    "DELETE FROM document_chunks WHERE document_id = %s AND user_id = %s",
                    (document_id, user_id),
                )
                connection.executemany(
                    """
                    INSERT INTO document_chunks (
                        id, user_id, document_id, chunk_index, content,
                        page_number, slide_number, content_hash
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    [
                        (
                            chunk.id,
                            user_id,
                            document_id,
                            chunk.chunk_index,
                            chunk.content,
                            chunk.page_number,
                            chunk.slide_number,
                            chunk.content_hash,
                        )
                        for chunk in chunks
                    ],
                )
                connection.execute(
                    """
                    UPDATE documents
                    SET status = 'chunked', error_message = NULL, updated_at = now()
                    WHERE id = %s AND user_id = %s AND status = 'processing'
                    """,
                    (document_id, user_id),
                )
                return True

    def fail_processing(self, user_id: UUID, document_id: UUID, message: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE documents
                SET status = 'failed', error_message = %s, updated_at = now()
                WHERE id = %s AND user_id = %s AND status IN ('processing', 'chunked')
                """,
                (message[:500], document_id, user_id),
            )

    def save_embeddings_and_mark_ready(
        self, user_id: UUID, document_id: UUID, embeddings: list[list[float]]
    ) -> bool:
        """Persist all vectors and expose the document only after the full index exists."""
        with self._connect() as connection:
            with connection.transaction():
                document = connection.execute(
                    """
                    SELECT status
                    FROM documents
                    WHERE id = %s AND user_id = %s AND deleted_at IS NULL
                    FOR UPDATE
                    """,
                    (document_id, user_id),
                ).fetchone()
                if document is None or document["status"] != "chunked":
                    return False

                chunks = connection.execute(
                    """
                    SELECT id
                    FROM document_chunks
                    WHERE document_id = %s AND user_id = %s
                    ORDER BY chunk_index
                    FOR UPDATE
                    """,
                    (document_id, user_id),
                ).fetchall()
                if not chunks or len(chunks) != len(embeddings):
                    raise RuntimeError("Embedding count does not match the document chunks")

                connection.executemany(
                    """
                    UPDATE document_chunks
                    SET embedding = %s::vector
                    WHERE id = %s AND document_id = %s AND user_id = %s
                    """,
                    [
                        (
                            "[" + ",".join(str(float(value)) for value in vector) + "]",
                            chunk["id"],
                            document_id,
                            user_id,
                        )
                        for chunk, vector in zip(chunks, embeddings, strict=True)
                    ],
                )
                updated = connection.execute(
                    """
                    UPDATE documents
                    SET status = 'ready', error_message = NULL, updated_at = now()
                    WHERE id = %s AND user_id = %s AND status = 'chunked'
                    RETURNING id
                    """,
                    (document_id, user_id),
                ).fetchone()
                return updated is not None

    def begin_delete(self, user_id: UUID, document_id: UUID) -> dict | None:
        with self._connect() as connection:
            with connection.transaction():
                document = connection.execute(
                    """
                    SELECT id, storage_key, status
                    FROM documents
                    WHERE id = %s AND user_id = %s
                    FOR UPDATE
                    """,
                    (document_id, user_id),
                ).fetchone()
                if document is None:
                    return None
                if document["status"] == "deleted":
                    return document
                return connection.execute(
                    """
                    UPDATE documents
                    SET status = 'deleting',
                        deleted_at = COALESCE(deleted_at, now()),
                        error_message = NULL,
                        updated_at = now()
                    WHERE id = %s AND user_id = %s
                    RETURNING id, storage_key, status
                    """,
                    (document_id, user_id),
                ).fetchone()

    def finish_delete(self, user_id: UUID, document_id: UUID) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE documents
                SET status = 'deleted', error_message = NULL, updated_at = now()
                WHERE id = %s AND user_id = %s AND status = 'deleting'
                """,
                (document_id, user_id),
            )

    def note_delete_failure(self, user_id: UUID, document_id: UUID) -> None:
        # Store a safe recovery hint; provider errors may contain sensitive details.
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE documents
                SET error_message = 'Storage cleanup pending', updated_at = now()
                WHERE id = %s AND user_id = %s AND status = 'deleting'
                """,
                (document_id, user_id),
            )
