from __future__ import annotations

import os
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row


class ChatRepository:
    def __init__(self, database_url: str | None = None) -> None:
        self._database_url = database_url

    def _connect(self) -> psycopg.Connection:
        database_url = self._database_url or os.getenv("DATABASE_URL")
        if not database_url:
            raise RuntimeError("DATABASE_URL is not configured")
        return psycopg.connect(database_url, row_factory=dict_row)

    def create_session(
        self, user_id: UUID, session_id: UUID, selected_document_ids: list[UUID] | None
    ) -> dict:
        with self._connect() as connection:
            with connection.transaction():
                if selected_document_ids is not None:
                    if not selected_document_ids:
                        raise ValueError("Select at least one ready document")
                    ready_ids = connection.execute(
                        """
                        SELECT id FROM documents
                        WHERE user_id = %s AND status = 'ready' AND id = ANY(%s)
                        """,
                        (user_id, selected_document_ids),
                    ).fetchall()
                    if {row["id"] for row in ready_ids} != set(selected_document_ids):
                        raise ValueError("One or more selected documents are unavailable")

                session = connection.execute(
                    """
                    INSERT INTO chat_sessions (id, user_id)
                    VALUES (%s, %s)
                    RETURNING id, title, created_at, updated_at
                    """,
                    (session_id, user_id),
                ).fetchone()
                if selected_document_ids is not None:
                    connection.executemany(
                        """
                        INSERT INTO chat_session_documents (user_id, session_id, document_id)
                        VALUES (%s, %s, %s)
                        """,
                        [(user_id, session_id, document_id) for document_id in selected_document_ids],
                    )
                session["selected_document_ids"] = selected_document_ids or []
                session["all_documents"] = selected_document_ids is None
                return session

    def list_sessions(self, user_id: UUID) -> list[dict]:
        with self._connect() as connection:
            return connection.execute(
                """
                SELECT s.id, s.title, s.created_at, s.updated_at,
                       count(DISTINCT m.id)::integer AS message_count,
                       COALESCE(array_agg(DISTINCT scope.document_id)
                           FILTER (WHERE scope.document_id IS NOT NULL), ARRAY[]::uuid[])
                           AS selected_document_ids,
                       count(DISTINCT scope.document_id) = 0 AS all_documents
                FROM chat_sessions AS s
                LEFT JOIN chat_messages AS m
                    ON m.session_id = s.id AND m.user_id = s.user_id
                LEFT JOIN chat_session_documents AS scope
                    ON scope.session_id = s.id AND scope.user_id = s.user_id
                WHERE s.user_id = %s
                GROUP BY s.id
                ORDER BY s.updated_at DESC, s.id DESC
                """,
                (user_id,),
            ).fetchall()

    def get_session(self, user_id: UUID, session_id: UUID) -> dict | None:
        with self._connect() as connection:
            return connection.execute(
                """
                SELECT id, user_id, title, created_at, updated_at
                FROM chat_sessions
                WHERE id = %s AND user_id = %s
                """,
                (session_id, user_id),
            ).fetchone()

    def get_session_document_ids(self, user_id: UUID, session_id: UUID) -> list[UUID]:
        with self._connect() as connection:
            return [
                row["document_id"]
                for row in connection.execute(
                    """
                    SELECT document_id FROM chat_session_documents
                    WHERE user_id = %s AND session_id = %s
                    ORDER BY document_id
                    """,
                    (user_id, session_id),
                ).fetchall()
            ]

    def list_messages(self, user_id: UUID, session_id: UUID) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT m.id, m.role, m.content, m.created_at,
                       COALESCE(
                           jsonb_agg(
                               jsonb_build_object(
                                   'rank', c.citation_rank,
                                   'excerpt', c.excerpt,
                                   'page_number', c.page_number,
                                   'slide_number', c.slide_number,
                                   'document_name', d.original_filename
                               ) ORDER BY c.citation_rank
                           ) FILTER (WHERE c.id IS NOT NULL),
                           '[]'::jsonb
                       ) AS citations
                FROM chat_messages AS m
                LEFT JOIN message_citations AS c
                    ON c.message_id = m.id AND c.user_id = m.user_id
                LEFT JOIN document_chunks AS dc ON dc.id = c.document_chunk_id
                LEFT JOIN documents AS d
                    ON d.id = dc.document_id AND d.user_id = dc.user_id
                WHERE m.user_id = %s AND m.session_id = %s
                GROUP BY m.id
                ORDER BY m.created_at, m.id
                """,
                (user_id, session_id),
            ).fetchall()
            return [dict(row) for row in rows]

    def recent_messages(self, user_id: UUID, session_id: UUID, limit: int = 8) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT role, content
                FROM chat_messages
                WHERE user_id = %s AND session_id = %s
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (user_id, session_id, limit),
            ).fetchall()
            return list(reversed(rows))

    def retrieve_chunks(
        self,
        user_id: UUID,
        session_id: UUID,
        query_embedding: list[float],
        limit: int = 6,
    ) -> list[dict]:
        vector = "[" + ",".join(str(float(value)) for value in query_embedding) + "]"
        with self._connect() as connection:
            return connection.execute(
                """
                SELECT c.id AS chunk_id, c.document_id, c.content, c.page_number,
                       c.slide_number, d.original_filename,
                       c.embedding <=> %s::vector AS distance
                FROM document_chunks AS c
                JOIN documents AS d
                  ON d.id = c.document_id AND d.user_id = c.user_id
                WHERE c.user_id = %s
                  AND d.status = 'ready'
                  AND c.embedding IS NOT NULL
                  AND (
                      NOT EXISTS (
                          SELECT 1 FROM chat_session_documents AS any_scope
                          WHERE any_scope.user_id = %s AND any_scope.session_id = %s
                      )
                      OR EXISTS (
                          SELECT 1 FROM chat_session_documents AS selected
                          WHERE selected.user_id = %s
                            AND selected.session_id = %s
                            AND selected.document_id = c.document_id
                      )
                  )
                ORDER BY c.embedding <=> %s::vector
                LIMIT %s
                """,
                (
                    vector,
                    user_id,
                    user_id,
                    session_id,
                    user_id,
                    session_id,
                    vector,
                    limit,
                ),
            ).fetchall()

    def save_turn(
        self,
        user_id: UUID,
        session_id: UUID,
        question: str,
        answer: str,
        citations: list[dict],
    ) -> dict:
        with self._connect() as connection:
            with connection.transaction():
                session = connection.execute(
                    """
                    SELECT id, title FROM chat_sessions
                    WHERE id = %s AND user_id = %s
                    FOR UPDATE
                    """,
                    (session_id, user_id),
                ).fetchone()
                if session is None:
                    raise LookupError("Chat session not found")

                user_message = connection.execute(
                    """
                    INSERT INTO chat_messages (id, user_id, session_id, role, content)
                    VALUES (%s, %s, %s, 'user', %s)
                    RETURNING id, role, content, created_at
                    """,
                    (uuid4(), user_id, session_id, question),
                ).fetchone()
                assistant_message = connection.execute(
                    """
                    INSERT INTO chat_messages (id, user_id, session_id, role, content)
                    VALUES (%s, %s, %s, 'assistant', %s)
                    RETURNING id, role, content, created_at
                    """,
                    (uuid4(), user_id, session_id, answer),
                ).fetchone()
                for rank, citation in enumerate(citations, start=1):
                    citation_insert = connection.execute(
                        """
                        INSERT INTO message_citations (
                            id, user_id, message_id, document_chunk_id,
                            citation_rank, excerpt, page_number, slide_number
                        )
                        SELECT %s, %s, %s, c.id, %s, %s, c.page_number, c.slide_number
                        FROM document_chunks AS c
                        JOIN documents AS d
                          ON d.id = c.document_id AND d.user_id = c.user_id
                        WHERE c.id = %s AND c.user_id = %s AND d.status = 'ready'
                          AND (
                              NOT EXISTS (
                                  SELECT 1 FROM chat_session_documents AS any_scope
                                  WHERE any_scope.user_id = %s AND any_scope.session_id = %s
                              )
                              OR EXISTS (
                                  SELECT 1 FROM chat_session_documents AS selected
                                  WHERE selected.user_id = %s AND selected.session_id = %s
                                    AND selected.document_id = c.document_id
                              )
                          )
                        """,
                        (
                            uuid4(),
                            user_id,
                            assistant_message["id"],
                            rank,
                            citation["excerpt"][:600],
                            citation["chunk_id"],
                            user_id,
                            user_id,
                            session_id,
                            user_id,
                            session_id,
                        ),
                    )
                    if citation_insert.rowcount != 1:
                        raise RuntimeError("Citation source is no longer available")

                connection.execute(
                    """
                    UPDATE chat_sessions
                    SET title = COALESCE(title, %s), updated_at = now()
                    WHERE id = %s AND user_id = %s
                    """,
                    (question[:80], session_id, user_id),
                )
                return {"user_message": user_message, "assistant_message": assistant_message}
