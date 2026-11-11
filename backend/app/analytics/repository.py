"""Aggregates behind the learning-data page.

Everything here is derived from rows other modules already write, so the page adds
no table and no background job: the review history and the current SM-2 state are
enough to describe how the student is doing.
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from uuid import UUID

import psycopg
from psycopg.rows import dict_row


# A card counts as mastered once its interval is long enough that it is reviewed
# roughly monthly; below that it is still being consolidated.
MASTERED_INTERVAL_DAYS = 21
UPCOMING_DAYS = 7
# Below this many reviews a percentage is noise, so it is reported as unavailable.
MIN_REVIEWS_FOR_RATE = 5


class AnalyticsRepository:
    def __init__(self, database_url: str | None = None) -> None:
        self._database_url = database_url

    def _connect(self) -> psycopg.Connection:
        database_url = self._database_url or os.getenv("DATABASE_URL")
        if not database_url:
            raise RuntimeError("DATABASE_URL is not configured")
        return psycopg.connect(database_url, row_factory=dict_row)

    def get_summary(self, user_id: UUID, timezone: str) -> dict:
        with self._connect() as connection:
            reviews = connection.execute(
                """
                SELECT count(*)::integer AS reviewed_total,
                       count(*) FILTER (WHERE quality >= 3)::integer AS correct_total,
                       (now() AT TIME ZONE %s)::date AS today
                FROM flashcard_reviews
                WHERE user_id = %s
                """,
                (timezone, user_id),
            ).fetchone()

            mastery = connection.execute(
                """
                SELECT count(*) FILTER (WHERE repetition_count = 0)::integer AS new_cards,
                       count(*) FILTER (WHERE repetition_count > 0
                                          AND interval_days < %s)::integer AS learning_cards,
                       count(*) FILTER (WHERE repetition_count > 0
                                          AND interval_days >= %s)::integer AS mastered_cards
                FROM flashcards
                WHERE user_id = %s
                """,
                (MASTERED_INTERVAL_DAYS, MASTERED_INTERVAL_DAYS, user_id),
            ).fetchone()

            upcoming = connection.execute(
                """
                SELECT (next_review_at AT TIME ZONE %s)::date AS day,
                       count(*)::integer AS card_count
                FROM flashcards
                WHERE user_id = %s
                  AND (next_review_at AT TIME ZONE %s)::date >= (now() AT TIME ZONE %s)::date
                  AND (next_review_at AT TIME ZONE %s)::date
                      < (now() AT TIME ZONE %s)::date + %s::integer
                GROUP BY day
                ORDER BY day
                """,
                (timezone, user_id, timezone, timezone, timezone, timezone, UPCOMING_DAYS),
            ).fetchall()

            # Only the distinct review days are needed for the streak; the bound keeps
            # a long-lived account from loading its whole history.
            recent_days = connection.execute(
                """
                SELECT DISTINCT (reviewed_at AT TIME ZONE %s)::date AS day
                FROM flashcard_reviews
                WHERE user_id = %s
                ORDER BY day DESC
                LIMIT 400
                """,
                (timezone, user_id),
            ).fetchall()

        reviewed_total = reviews["reviewed_total"]
        correct_rate = (
            round(reviews["correct_total"] / reviewed_total, 3)
            if reviewed_total >= MIN_REVIEWS_FOR_RATE
            else None
        )

        return {
            "reviewed_total": reviewed_total,
            "correct_rate": correct_rate,
            "streak_days": _streak(reviews["today"], [row["day"] for row in recent_days]),
            "mastery": {
                "new": mastery["new_cards"],
                "learning": mastery["learning_cards"],
                "mastered": mastery["mastered_cards"],
            },
            "upcoming": [
                {"date": row["day"], "count": row["card_count"]} for row in upcoming
            ],
        }


def _streak(today: date, review_days: list[date]) -> int:
    """Consecutive review days ending today, or yesterday when today has none.

    Ending at yesterday is deliberate: a student who has not reviewed yet today has
    not broken the streak, and reporting 0 all morning would be discouraging.
    """
    if not review_days:
        return 0
    present = set(review_days)
    cursor = today if today in present else today - timedelta(days=1)
    streak = 0
    while cursor in present:
        streak += 1
        cursor -= timedelta(days=1)
    return streak
