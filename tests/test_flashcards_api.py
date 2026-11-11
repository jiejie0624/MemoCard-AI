import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from uuid import UUID, uuid4

from fastapi import HTTPException

from backend.app.auth.routes import PublicUser, current_user
from backend.app.chat.provider import ChatProviderError
from backend.app.flashcards.routes import get_flashcard_provider, get_flashcard_repository
from backend.app.main import app


class FakeFlashcardRepository:
    def __init__(self, user_id):
        self.user_id = user_id
        self.source_id = uuid4()
        self.answer = {
            "message": {"id": self.source_id, "content": "Spaced repetition reviews knowledge at increasing intervals [S1]."},
            "citations": [{
                "citation_rank": 1, "document_id": uuid4(), "document_chunk_id": uuid4(),
                "excerpt": "Intervals increase as recall succeeds.", "page_number": 4,
                "slide_number": None, "original_filename": "biology.pdf",
            }],
        }
        self.created = []

    def get_cited_answer(self, user_id, message_id):
        return self.answer if user_id == self.user_id and message_id == self.source_id else None

    def create_cards(self, user_id, source_message_id, cards, citations):
        self.created = cards
        now = datetime.now(timezone.utc)
        return [
            {
                "id": uuid4(), "source_message_id": source_message_id,
                "question": card["question"], "answer": card["answer"],
                "repetition_count": 0, "ease_factor": 2.5, "interval_days": 0,
                "last_reviewed_at": None, "next_review_at": now,
                "created_at": now, "updated_at": now,
                "sources": [{"document_id": citations[0]["document_id"],
                             "document_name": citations[0]["original_filename"],
                             "document_chunk_id": citations[0]["document_chunk_id"]}],
            }
            for card in cards
        ]

    def list_cards(self, user_id):
        return []

    def get_card(self, user_id, card_id):
        if user_id != self.user_id:
            return None
        return {
            "id": card_id,
            "question": "How does spaced repetition help?",
            "answer": "It increases the review intervals as recall succeeds.",
        }


class FakeFlashcardProvider:
    def __init__(self):
        self.response = json.dumps({"cards": [{
            "question": "How does spaced repetition help?",
            "answer": "It increases the review intervals as recall succeeds.",
            "source_refs": [1],
        }]})
        self.called = False

    def complete(self, messages, response_format=None):
        self.called = True
        self.response_format = response_format
        return self.response


async def asgi_request(method, path, body=b"", headers=None):
    request_headers = [(b"host", b"testserver"), (b"accept", b"application/json")]
    request_headers.extend((key.lower().encode(), value.encode()) for key, value in (headers or {}).items())
    scope = {
        "type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1", "method": method, "scheme": "http", "path": path,
        "raw_path": path.encode("ascii"), "query_string": b"", "root_path": "",
        "headers": request_headers, "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80), "state": {},
    }
    received = False
    events = []

    async def receive():
        nonlocal received
        if received:
            return {"type": "http.disconnect"}
        received = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(event):
        events.append(event)

    await app(scope, receive, send)
    response = next(event for event in events if event["type"] == "http.response.start")
    content = b"".join(event.get("body", b"") for event in events if event["type"] == "http.response.body")
    return response["status"], content


class FlashcardApiTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.user_id = uuid4()
        self.user = PublicUser(
            id=self.user_id, email="student@example.edu", display_name="Student",
            timezone="Asia/Kuala_Lumpur", created_at=datetime.now(timezone.utc),
        )
        self.repository = FakeFlashcardRepository(self.user_id)
        self.provider = FakeFlashcardProvider()
        app.dependency_overrides[current_user] = lambda: self.user
        app.dependency_overrides[get_flashcard_repository] = lambda: self.repository
        app.dependency_overrides[get_flashcard_provider] = lambda: self.provider

    def tearDown(self):
        app.dependency_overrides.clear()

    async def test_generate_returns_unsaved_draft_and_save_persists_after_confirmation(self):
        status_code, body = await asgi_request(
            "POST", "/api/flashcards/generate",
            json.dumps({"source_message_id": str(self.repository.source_id)}).encode(),
            {"content-type": "application/json"},
        )
        draft = json.loads(body)
        self.assertEqual(status_code, 200)
        self.assertEqual(draft["cards"][0]["source_refs"], [1])
        self.assertEqual(self.repository.created, [])
        self.assertEqual(self.provider.response_format, {"type": "json_object"})

        status_code, body = await asgi_request(
            "POST", "/api/flashcards",
            json.dumps(draft).encode(),
            {"content-type": "application/json"},
        )
        self.assertEqual(status_code, 201)
        saved = json.loads(body)
        self.assertEqual(saved[0]["question"], draft["cards"][0]["question"])
        self.assertEqual(saved[0]["sources"][0]["document_name"], "biology.pdf")
        self.assertEqual(len(self.repository.created), 1)

    async def test_foreign_source_and_invalid_model_reference_are_rejected(self):
        other_source_id = uuid4()
        status_code, _ = await asgi_request(
            "POST", "/api/flashcards/generate",
            json.dumps({"source_message_id": str(other_source_id)}).encode(),
            {"content-type": "application/json"},
        )
        self.assertEqual(status_code, 404)
        self.assertFalse(self.provider.called)

        self.provider.response = json.dumps({"cards": [{
            "question": "Unfounded card", "answer": "Answer", "source_refs": [9],
        }]})
        status_code, _ = await asgi_request(
            "POST", "/api/flashcards/generate",
            json.dumps({"source_message_id": str(self.repository.source_id)}).encode(),
            {"content-type": "application/json"},
        )
        self.assertEqual(status_code, 502)
        self.assertEqual(self.repository.created, [])

    async def test_provider_failure_returns_retryable_error_without_writes(self):
        self.provider.complete = lambda *_args, **_kwargs: (_ for _ in ()).throw(ChatProviderError("offline"))
        status_code, _ = await asgi_request(
            "POST", "/api/flashcards/generate",
            json.dumps({"source_message_id": str(self.repository.source_id)}).encode(),
            {"content-type": "application/json"},
        )
        self.assertEqual(status_code, 502)
        self.assertEqual(self.repository.created, [])

    async def test_answer_check_returns_a_binary_verdict(self):
        self.provider.response = json.dumps({"correct": True, "feedback": "You named the key idea."})
        status_code, body = await asgi_request(
            "POST", f"/api/flashcards/{uuid4()}/answer-check",
            json.dumps({"answer": "Intervals grow as you remember."}).encode(),
            {"content-type": "application/json"},
        )
        self.assertEqual(status_code, 200)
        verdict = json.loads(body)
        self.assertTrue(verdict["correct"])
        self.assertEqual(verdict["feedback"], "You named the key idea.")
        self.assertEqual(self.provider.response_format, {"type": "json_object"})

    async def test_answer_check_rejects_a_malformed_verdict(self):
        # "correct" must be a real boolean: a truthy string would mark every answer right.
        self.provider.response = json.dumps({"correct": "yes"})
        status_code, _ = await asgi_request(
            "POST", f"/api/flashcards/{uuid4()}/answer-check",
            json.dumps({"answer": "Something"}).encode(),
            {"content-type": "application/json"},
        )
        self.assertEqual(status_code, 502)


if __name__ == "__main__":
    unittest.main()
