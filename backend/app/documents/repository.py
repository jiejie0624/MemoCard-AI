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
