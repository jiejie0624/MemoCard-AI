from __future__ import annotations

import os
from datetime import date
from uuid import UUID

import psycopg
from psycopg.rows import dict_row


class CalendarRepository:
    def __init__(self, database_url: str | None = None) -> None:
        self._database_url = database_url

    def _connect(self) -> psycopg.Connection:
        database_url = self._database_url or os.getenv("DATABASE_URL")
        if not database_url:
            raise RuntimeError("DATABASE_URL is not configured")
        return psycopg.connect(database_url, row_factory=dict_row)

    def get_summary(self, user_id: UUID, timezone_name: str) -> dict:
        with self._connect() as connection:
            return connection.execute(
                """
                WITH local_clock AS (
                    SELECT now() AT TIME ZONE %s AS local_now
                ), boundaries AS (
                    SELECT local_now::date AS local_today,
                           local_now::date::timestamp AT TIME ZONE %s AS today_start,
                           (local_now::date + 1)::timestamp AT TIME ZONE %s AS tomorrow_start,
                           (local_now::date + 8)::timestamp AT TIME ZONE %s AS week_end
                    FROM local_clock
                )
                SELECT boundaries.local_today AS today,
                       count(*) FILTER (
                           WHERE f.next_review_at < boundaries.today_start
                       )::integer AS overdue_count,
                       count(*) FILTER (
                           WHERE f.next_review_at >= boundaries.today_start
                             AND f.next_review_at < boundaries.tomorrow_start
                       )::integer AS today_count,
                       count(*) FILTER (
                           WHERE f.next_review_at >= boundaries.tomorrow_start
                             AND f.next_review_at < boundaries.week_end
                       )::integer AS upcoming_count,
                       min(f.next_review_at) FILTER (
                           WHERE f.next_review_at >= boundaries.today_start
                       ) AS next_review_at
                FROM boundaries
                LEFT JOIN flashcards AS f ON f.user_id = %s
                GROUP BY boundaries.local_today
                """,
                (timezone_name, timezone_name, timezone_name, timezone_name, user_id),
            ).fetchone()

    def get_day_counts(
        self, user_id: UUID, timezone_name: str, start_date: date, end_date: date
    ) -> list[dict]:
        with self._connect() as connection:
            return connection.execute(
                """
                SELECT (f.next_review_at AT TIME ZONE %s)::date AS due_date,
                       count(*)::integer AS card_count
                FROM flashcards AS f
                WHERE f.user_id = %s
                  AND f.next_review_at >= (%s::date::timestamp AT TIME ZONE %s)
                  AND f.next_review_at < ((%s::date + 1)::timestamp AT TIME ZONE %s)
                GROUP BY due_date
                ORDER BY due_date
                """,
                (timezone_name, user_id, start_date, timezone_name, end_date, timezone_name),
            ).fetchall()

    def get_day_cards(self, user_id: UUID, timezone_name: str, due_date: date) -> list[dict]:
        with self._connect() as connection:
            return connection.execute(
                """
                SELECT f.id, f.question, f.answer, f.next_review_at,
                       COALESCE(
                           array_agg(DISTINCT d.original_filename)
                               FILTER (WHERE d.id IS NOT NULL),
                           ARRAY[]::text[]
                       ) AS source_names
                FROM flashcards AS f
                LEFT JOIN flashcard_sources AS fs
                  ON fs.flashcard_id = f.id AND fs.user_id = f.user_id
                LEFT JOIN documents AS d
                  ON d.id = fs.document_id AND d.user_id = fs.user_id
                WHERE f.user_id = %s
                  AND f.next_review_at >= (%s::date::timestamp AT TIME ZONE %s)
                  AND f.next_review_at < ((%s::date + 1)::timestamp AT TIME ZONE %s)
                GROUP BY f.id
                ORDER BY f.next_review_at, f.created_at, f.id
                """,
                (user_id, due_date, timezone_name, due_date, timezone_name),
            ).fetchall()
