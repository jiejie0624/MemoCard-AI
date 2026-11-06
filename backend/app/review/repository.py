import os
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import psycopg
from psycopg.rows import dict_row

from backend.app.review.sm2 import SM2State, calculate_next_state


class CardNotDueError(Exception):
    """Raised when a user tries to grade a card before its scheduled date."""


class IdempotencyConflictError(Exception):
    """Raised when a request key is reused for a different review payload."""


class InvalidUserTimezoneError(Exception):
    """Raised when a stored timezone cannot be used for calendar scheduling."""


@dataclass(frozen=True)
class ReviewOutcome:
    review_id: UUID
    flashcard_id: UUID
    quality: int
    reviewed_at: datetime
    repetition_count: int
    ease_factor: Decimal
    interval_days: int
    next_review_at: datetime
    idempotent: bool


def next_review_midnight(
    reviewed_at: datetime,
    interval_days: int,
    timezone_name: str,
) -> datetime:
    """Calculate the next due date at local midnight and return it as UTC."""
    if reviewed_at.tzinfo is None or reviewed_at.utcoffset() is None:
        raise ValueError("Review timestamp must be timezone-aware")
    if type(interval_days) is not int or interval_days < 1:
        raise ValueError("Review interval must be a positive integer")

    try:
        user_timezone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, TypeError) as error:
        raise InvalidUserTimezoneError("The account timezone is not a valid IANA timezone") from error

    next_date = reviewed_at.astimezone(user_timezone).date() + timedelta(days=interval_days)
    local_midnight = datetime.combine(next_date, time.min, tzinfo=user_timezone)
    return local_midnight.astimezone(timezone.utc)


class PostgresReviewRepository:
    def __init__(self, database_url: str | None = None) -> None:
        self._database_url = database_url

    def _connect(self) -> psycopg.Connection:
        database_url = self._database_url or os.getenv("DATABASE_URL")
        if not database_url:
            raise RuntimeError("DATABASE_URL is not configured")
        return psycopg.connect(database_url, row_factory=dict_row)

    def record_review(
        self,
        user_id: UUID,
        flashcard_id: UUID,
        idempotency_key: UUID,
        quality: int,
    ) -> ReviewOutcome | None:
        reviewed_at = datetime.now(timezone.utc)

        with self._connect() as connection:
            with connection.transaction():
                card = connection.execute(
                    """
                    SELECT flashcards.id, flashcards.repetition_count,
                           flashcards.ease_factor, flashcards.interval_days,
                           flashcards.next_review_at, users.timezone
                    FROM flashcards
                    JOIN users ON users.id = flashcards.user_id
                    WHERE flashcards.id = %s AND flashcards.user_id = %s
                    FOR UPDATE OF flashcards
                    """,
                    (flashcard_id, user_id),
                ).fetchone()
                if card is None:
                    return None

                existing = self._get_review_by_key(connection, user_id, idempotency_key)
                if existing is not None:
                    return self._return_existing(existing, flashcard_id, quality)

                if card["next_review_at"] > reviewed_at:
                    raise CardNotDueError

                previous_state = SM2State(
                    repetition_count=card["repetition_count"],
                    ease_factor=card["ease_factor"],
                    interval_days=card["interval_days"],
                )
                next_state = calculate_next_state(previous_state, quality)
                next_review_at = next_review_midnight(
                    reviewed_at,
                    next_state.interval_days,
                    card["timezone"],
                )
                review_id = uuid4()

                inserted = connection.execute(
                    """
                    INSERT INTO flashcard_reviews (
                        id, user_id, flashcard_id, quality, reviewed_at,
                        repetition_count_before, repetition_count_after,
                        interval_days_before, interval_days_after,
                        ease_factor_before, ease_factor_after, next_review_at_after,
                        idempotency_key
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (user_id, idempotency_key) DO NOTHING
                    RETURNING id
                    """,
                    (
                        review_id,
                        user_id,
                        flashcard_id,
                        quality,
                        reviewed_at,
                        previous_state.repetition_count,
                        next_state.repetition_count,
                        previous_state.interval_days,
                        next_state.interval_days,
                        previous_state.ease_factor,
                        next_state.ease_factor,
                        next_review_at,
                        idempotency_key,
                    ),
                ).fetchone()

                if inserted is None:
                    raced_review = self._get_review_by_key(connection, user_id, idempotency_key)
                    if raced_review is None:
                        raise RuntimeError("Review idempotency conflict could not be resolved")
                    return self._return_existing(raced_review, flashcard_id, quality)

                connection.execute(
                    """
                    UPDATE flashcards
                    SET repetition_count = %s,
                        ease_factor = %s,
                        interval_days = %s,
                        last_reviewed_at = %s,
                        next_review_at = %s,
                        updated_at = now()
                    WHERE id = %s AND user_id = %s
                    """,
                    (
                        next_state.repetition_count,
                        next_state.ease_factor,
                        next_state.interval_days,
                        reviewed_at,
                        next_review_at,
                        flashcard_id,
                        user_id,
                    ),
                )

                return ReviewOutcome(
                    review_id=review_id,
                    flashcard_id=flashcard_id,
                    quality=quality,
                    reviewed_at=reviewed_at,
                    repetition_count=next_state.repetition_count,
                    ease_factor=next_state.ease_factor,
                    interval_days=next_state.interval_days,
                    next_review_at=next_review_at,
                    idempotent=False,
                )

    @staticmethod
    def _get_review_by_key(
        connection,
        user_id: UUID,
        idempotency_key: UUID,
    ) -> dict | None:
        return connection.execute(
            """
            SELECT id, flashcard_id, quality, reviewed_at,
                   repetition_count_after, ease_factor_after, interval_days_after,
                   next_review_at_after
            FROM flashcard_reviews
            WHERE user_id = %s AND idempotency_key = %s
            """,
            (user_id, idempotency_key),
        ).fetchone()

    @staticmethod
    def _return_existing(
        row: dict,
        flashcard_id: UUID,
        quality: int,
    ) -> ReviewOutcome:
        if row["flashcard_id"] != flashcard_id or row["quality"] != quality:
            raise IdempotencyConflictError
        return ReviewOutcome(
            review_id=row["id"],
            flashcard_id=row["flashcard_id"],
            quality=row["quality"],
            reviewed_at=row["reviewed_at"],
            repetition_count=row["repetition_count_after"],
            ease_factor=row["ease_factor_after"],
            interval_days=row["interval_days_after"],
            next_review_at=row["next_review_at_after"],
            idempotent=True,
        )
