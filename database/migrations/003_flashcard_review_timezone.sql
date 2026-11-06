-- Persist each user's calendar timezone and make review writes idempotent.
BEGIN;

ALTER TABLE users
    ADD COLUMN timezone TEXT NOT NULL DEFAULT 'UTC'
        CHECK (length(btrim(timezone)) > 0);

ALTER TABLE flashcard_reviews
    ADD COLUMN idempotency_key UUID;

-- Existing review rows become addressable by their own stable event IDs.
UPDATE flashcard_reviews
SET idempotency_key = id
WHERE idempotency_key IS NULL;

ALTER TABLE flashcard_reviews
    ALTER COLUMN idempotency_key SET NOT NULL;

CREATE UNIQUE INDEX flashcard_reviews_user_idempotency_uq
    ON flashcard_reviews (user_id, idempotency_key);

COMMIT;
