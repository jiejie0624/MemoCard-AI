from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from backend.app.auth.routes import PublicUser, current_user
from backend.app.review.repository import (
    CardNotDueError,
    IdempotencyConflictError,
    InvalidUserTimezoneError,
    PostgresReviewRepository,
)


router = APIRouter(prefix="/flashcards", tags=["flashcards"])


class ReviewSubmission(BaseModel):
    quality: int = Field(ge=0, le=5, strict=True)
    idempotency_key: UUID


class ReviewResponse(BaseModel):
    review_id: UUID
    flashcard_id: UUID
    quality: int
    reviewed_at: datetime
    repetition_count: int
    ease_factor: Decimal
    interval_days: int
    next_review_at: datetime
    idempotent: bool


def get_review_repository() -> PostgresReviewRepository:
    return PostgresReviewRepository()


ReviewRepository = Annotated[PostgresReviewRepository, Depends(get_review_repository)]
AuthenticatedUser = Annotated[PublicUser, Depends(current_user)]


@router.post(
    "/{flashcard_id}/reviews",
    response_model=ReviewResponse,
    status_code=status.HTTP_200_OK,
)
def submit_review(
    flashcard_id: UUID,
    payload: ReviewSubmission,
    user: AuthenticatedUser,
    repository: ReviewRepository,
) -> ReviewResponse:
    try:
        outcome = repository.record_review(
            user.id,
            flashcard_id,
            payload.idempotency_key,
            payload.quality,
        )
    except CardNotDueError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This flashcard is not due for review yet",
        ) from error
    except IdempotencyConflictError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This review request key was already used for a different review",
        ) from error
    except InvalidUserTimezoneError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The account timezone is not configured correctly",
        ) from error

    if outcome is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flashcard not found")

    return ReviewResponse(
        review_id=outcome.review_id,
        flashcard_id=outcome.flashcard_id,
        quality=outcome.quality,
        reviewed_at=outcome.reviewed_at,
        repetition_count=outcome.repetition_count,
        ease_factor=outcome.ease_factor,
        interval_days=outcome.interval_days,
        next_review_at=outcome.next_review_at,
        idempotent=outcome.idempotent,
    )
