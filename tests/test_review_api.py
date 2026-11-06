import unittest
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError

from backend.app.auth.routes import PublicUser, ProfileUpdate
from backend.app.review.repository import (
    CardNotDueError,
    IdempotencyConflictError,
    PostgresReviewRepository,
    ReviewOutcome,
    next_review_midnight,
)
from backend.app.review.routes import ReviewSubmission, submit_review


class FakeReviewRepository:
    def __init__(self, outcome: ReviewOutcome | None = None, error: Exception | None = None) -> None:
        self.outcome = outcome
        self.error = error
        self.calls: list[tuple] = []

    def record_review(self, user_id, flashcard_id, idempotency_key, quality):
        self.calls.append((user_id, flashcard_id, idempotency_key, quality))
        if self.error:
            raise self.error
        return self.outcome


class ReviewApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.user = PublicUser(
            id=uuid4(),
            email="student@example.edu",
            display_name="Student",
            timezone="Asia/Kuala_Lumpur",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        self.flashcard_id = uuid4()
        self.idempotency_key = uuid4()
        self.reviewed_at = datetime(2026, 2, 1, 3, tzinfo=timezone.utc)
        self.next_review_at = datetime(2026, 2, 1, 16, tzinfo=timezone.utc)

    def test_submit_review_returns_updated_state(self) -> None:
        repository = FakeReviewRepository(
            ReviewOutcome(
                review_id=uuid4(),
                flashcard_id=self.flashcard_id,
                quality=4,
                reviewed_at=self.reviewed_at,
                repetition_count=1,
                ease_factor=Decimal("2.500"),
                interval_days=1,
                next_review_at=self.next_review_at,
                idempotent=False,
            )
        )

        response = submit_review(
            self.flashcard_id,
            ReviewSubmission(quality=4, idempotency_key=self.idempotency_key),
            self.user,
            repository,
        )

        self.assertEqual(response.flashcard_id, self.flashcard_id)
        self.assertEqual(response.interval_days, 1)
        self.assertEqual(response.ease_factor, Decimal("2.500"))
        self.assertFalse(response.idempotent)
        self.assertEqual(repository.calls[0][0], self.user.id)

    def test_missing_or_not_due_cards_return_conflict_or_not_found(self) -> None:
        payload = ReviewSubmission(quality=4, idempotency_key=self.idempotency_key)
        with self.assertRaises(HTTPException) as missing:
            submit_review(self.flashcard_id, payload, self.user, FakeReviewRepository())
        self.assertEqual(missing.exception.status_code, 404)

        with self.assertRaises(HTTPException) as not_due:
            submit_review(
                self.flashcard_id,
                payload,
                self.user,
                FakeReviewRepository(error=CardNotDueError()),
            )
        self.assertEqual(not_due.exception.status_code, 409)

    def test_reused_key_with_different_payload_returns_conflict(self) -> None:
        with self.assertRaises(HTTPException) as conflict:
            submit_review(
                self.flashcard_id,
                ReviewSubmission(quality=4, idempotency_key=self.idempotency_key),
                self.user,
                FakeReviewRepository(error=IdempotencyConflictError()),
            )
        self.assertEqual(conflict.exception.status_code, 409)

    def test_quality_must_be_a_strict_integer_between_zero_and_five(self) -> None:
        for quality in (-1, 6, True, "4"):
            with self.subTest(quality=quality):
                with self.assertRaises(ValidationError):
                    ReviewSubmission(quality=quality, idempotency_key=self.idempotency_key)

    def test_timezone_schedule_uses_local_midnight_across_daylight_saving(self) -> None:
        reviewed_at = datetime(2026, 3, 8, 5, 30, tzinfo=timezone.utc)

        next_due = next_review_midnight(reviewed_at, 1, "America/New_York")

        self.assertEqual(next_due, datetime(2026, 3, 9, 4, tzinfo=timezone.utc))

    def test_profile_timezone_must_be_a_valid_iana_name(self) -> None:
        with self.assertRaises(ValidationError):
            ProfileUpdate(timezone="Not/A_Real_Zone")

    def test_duplicate_review_response_uses_stored_result(self) -> None:
        review_id = uuid4()
        row = {
            "id": review_id,
            "flashcard_id": self.flashcard_id,
            "quality": 4,
            "reviewed_at": self.reviewed_at,
            "repetition_count_after": 1,
            "ease_factor_after": Decimal("2.500"),
            "interval_days_after": 1,
            "next_review_at_after": self.next_review_at,
        }

        result = PostgresReviewRepository._return_existing(
            row,
            self.flashcard_id,
            4,
        )

        self.assertEqual(result.review_id, review_id)
        self.assertTrue(result.idempotent)


if __name__ == "__main__":
    unittest.main()
