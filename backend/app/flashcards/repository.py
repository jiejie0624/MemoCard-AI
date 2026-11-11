from __future__ import annotations

import os
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row


class FlashcardRepository:
    def __init__(self, database_url: str | None = None) -> None:
        self._database_url = database_url

    def _connect(self) -> psycopg.Connection:
        database_url = self._database_url or os.getenv("DATABASE_URL")
        if not database_url:
            raise RuntimeError("DATABASE_URL is not configured")
        return psycopg.connect(database_url, row_factory=dict_row)

    def get_cited_answer(self, user_id: UUID, message_id: UUID) -> dict | None:
        with self._connect() as connection:
            message = connection.execute(
                """
                SELECT id, content FROM chat_messages
                WHERE id = %s AND user_id = %s AND role = 'assistant'
                """,
                (message_id, user_id),
            ).fetchone()
            if message is None:
                return None
            citations = connection.execute(
                """
                SELECT c.citation_rank, chunk.document_id, c.document_chunk_id, c.excerpt,
                       c.page_number, c.slide_number, d.original_filename
                FROM message_citations AS c
                JOIN document_chunks AS chunk
                  ON chunk.id = c.document_chunk_id AND chunk.user_id = c.user_id
                JOIN documents AS d
                  ON d.id = chunk.document_id AND d.user_id = chunk.user_id
                WHERE c.message_id = %s AND c.user_id = %s
                ORDER BY c.citation_rank
                """,
                (message_id, user_id),
            ).fetchall()
            return {"message": message, "citations": citations}

    def create_cards(
        self,
        user_id: UUID,
        source_message_id: UUID,
        cards: list[dict],
        citations: list[dict],
    ) -> list[dict]:
        citation_by_rank = {row["citation_rank"]: row for row in citations}
        with self._connect() as connection:
            with connection.transaction():
                source = connection.execute(
                    """
                    SELECT id FROM chat_messages
                    WHERE id = %s AND user_id = %s AND role = 'assistant'
                    FOR SHARE
                    """,
                    (source_message_id, user_id),
                ).fetchone()
                if source is None:
                    raise LookupError("Source answer is unavailable")

                created_ids = []
                for card in cards:
                    source_rows = [citation_by_rank[rank] for rank in card["source_refs"]]
                    card_id = uuid4()
                    connection.execute(
                        """
                        INSERT INTO flashcards (id, user_id, source_message_id, question, answer)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (card_id, user_id, source_message_id, card["question"], card["answer"]),
                    )
                    unique_chunks: set[UUID] = set()
                    for source_row in source_rows:
                        chunk_id = source_row["document_chunk_id"]
                        if chunk_id in unique_chunks:
                            continue
                        unique_chunks.add(chunk_id)
                        connection.execute(
                            """
                            INSERT INTO flashcard_sources (
                                id, user_id, flashcard_id, document_id, document_chunk_id
                            )
                            SELECT %s, %s, %s, chunk.document_id, chunk.id
                            FROM document_chunks AS chunk
                            WHERE chunk.id = %s AND chunk.user_id = %s
                            """,
                            (uuid4(), user_id, card_id, chunk_id, user_id),
                        )
                    created_ids.append(card_id)

                return self._get_cards(connection, user_id, created_ids)

    @staticmethod
    def _get_cards(connection, user_id: UUID, card_ids: list[UUID] | None = None) -> list[dict]:
        rows = connection.execute(
            """
            SELECT f.id, f.source_message_id, f.question, f.answer,
                   f.repetition_count, f.ease_factor, f.interval_days,
                   f.last_reviewed_at, f.next_review_at, f.created_at, f.updated_at,
                   COALESCE(
                       jsonb_agg(jsonb_build_object(
                           'document_id', d.id,
                           'document_name', d.original_filename,
                           'document_chunk_id', fs.document_chunk_id
                       )) FILTER (WHERE fs.id IS NOT NULL),
                       '[]'::jsonb
                   ) AS sources
            FROM flashcards AS f
            LEFT JOIN flashcard_sources AS fs
              ON fs.flashcard_id = f.id AND fs.user_id = f.user_id
            LEFT JOIN documents AS d
              ON d.id = fs.document_id AND d.user_id = fs.user_id
            WHERE f.user_id = %s AND (%s::uuid[] IS NULL OR f.id = ANY(%s))
            GROUP BY f.id
            ORDER BY f.next_review_at, f.created_at DESC, f.id
            """,
            (user_id, card_ids, card_ids),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_cards(self, user_id: UUID) -> list[dict]:
        with self._connect() as connection:
            return self._get_cards(connection, user_id)

    def get_card(self, user_id: UUID, card_id: UUID) -> dict | None:
        with self._connect() as connection:
            cards = self._get_cards(connection, user_id, [card_id])
            return cards[0] if cards else None

    def update_card(self, user_id: UUID, card_id: UUID, question: str, answer: str) -> dict | None:
        with self._connect() as connection:
            updated = connection.execute(
                """
                UPDATE flashcards
                SET question = %s, answer = %s, updated_at = now()
                WHERE id = %s AND user_id = %s
                RETURNING id
                """,
                (question, answer, card_id, user_id),
            ).fetchone()
            if updated is None:
                return None
            rows = self._get_cards(connection, user_id, [card_id])
            return rows[0] if rows else None

    def delete_card(self, user_id: UUID, card_id: UUID) -> bool:
        with self._connect() as connection:
            result = connection.execute(
                "DELETE FROM flashcards WHERE id = %s AND user_id = %s",
                (card_id, user_id),
            )
            return result.rowcount == 1
