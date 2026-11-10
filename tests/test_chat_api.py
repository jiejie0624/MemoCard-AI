import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from uuid import UUID, uuid4

from fastapi import HTTPException

from backend.app.auth.routes import PublicUser, current_user
from backend.app.chat.provider import ChatProviderError
from backend.app.chat.routes import get_chat_embedder, get_chat_provider, get_chat_repository
from backend.app.main import app


class FakeChatRepository:
    def __init__(self, user_id: UUID) -> None:
        self.user_id = user_id
        self.sessions: dict[UUID, dict] = {}
        self.chunks = [{
            "chunk_id": uuid4(),
            "content": "Spaced repetition uses increasing review intervals.",
            "original_filename": "study-notes.txt",
            "page_number": 2,
            "slide_number": None,
        }]
        self.saved_turns = []

    def create_session(self, user_id, session_id, selected_document_ids):
        row = {
            "id": session_id,
            "title": None,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "selected_document_ids": selected_document_ids or [],
            "all_documents": selected_document_ids is None,
        }
        self.sessions[session_id] = row
        return row

    def list_sessions(self, user_id):
        return list(self.sessions.values()) if user_id == self.user_id else []

    def get_session(self, user_id, session_id):
        return self.sessions.get(session_id) if user_id == self.user_id else None

    def retrieve_chunks(self, user_id, session_id, query_embedding, limit=6):
        if user_id != self.user_id or session_id not in self.sessions:
            return []
        return self.chunks[:limit]

    def recent_messages(self, user_id, session_id, limit=8):
        return []

    def save_turn(self, user_id, session_id, question, answer, citations):
        self.saved_turns.append((question, answer, citations))

    def list_messages(self, user_id, session_id):
        if not self.saved_turns:
            return []
        question, answer, citations = self.saved_turns[-1]
        return [
            {"id": uuid4(), "role": "user", "content": question,
             "created_at": datetime.now(timezone.utc), "citations": []},
            {"id": uuid4(), "role": "assistant", "content": answer,
             "created_at": datetime.now(timezone.utc), "citations": [
                 {"rank": index, "excerpt": citation["excerpt"], "page_number": 2,
                  "slide_number": None, "document_name": "study-notes.txt"}
                 for index, citation in enumerate(citations, start=1)
             ]},
        ]


class FakeEmbedder:
    def embed_query(self, text):
        return [0.0] * 384


class FakeProvider:
    def __init__(self, answer="SM-2 adjusts intervals [S1]."):
        self.answer = answer
        self.fail = False

    def complete(self, messages):
        if self.fail:
            raise ChatProviderError("provider unavailable")
        self.messages = messages
        return self.answer


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


class ChatApiTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.user_id = uuid4()
        self.user = PublicUser(
            id=self.user_id, email="student@example.edu", display_name="Student",
            timezone="Asia/Kuala_Lumpur", created_at=datetime.now(timezone.utc),
        )
        self.repository = FakeChatRepository(self.user_id)
        self.embedder = FakeEmbedder()
        self.provider = FakeProvider()
        self.authenticated = True

        def get_user():
            if not self.authenticated:
                raise HTTPException(status_code=401, detail="Not authenticated")
            return self.user

        app.dependency_overrides[current_user] = get_user
        app.dependency_overrides[get_chat_repository] = lambda: self.repository
        app.dependency_overrides[get_chat_embedder] = lambda: self.embedder
        app.dependency_overrides[get_chat_provider] = lambda: self.provider

    def tearDown(self):
        app.dependency_overrides.clear()

    async def test_question_returns_persisted_answer_and_valid_source(self):
        status_code, body = await asgi_request(
            "POST", "/api/chat/sessions", json.dumps({}).encode(),
            {"content-type": "application/json"},
        )
        self.assertEqual(status_code, 201)
        session_id = json.loads(body)["id"]

        status_code, body = await asgi_request(
            "POST", f"/api/chat/sessions/{session_id}/messages",
            json.dumps({"question": "How does spaced repetition work?"}).encode(),
            {"content-type": "application/json"},
        )
        self.assertEqual(status_code, 200)
        messages = json.loads(body)
        self.assertEqual(messages[1]["content"], "SM-2 adjusts intervals [S1].")
        self.assertEqual(messages[1]["citations"][0]["document_name"], "study-notes.txt")
        self.assertEqual(len(self.repository.saved_turns), 1)

    async def test_unavailable_evidence_and_provider_failure_do_not_save_turn(self):
        _, body = await asgi_request(
            "POST", "/api/chat/sessions", b"{}", {"content-type": "application/json"}
        )
        session_id = json.loads(body)["id"]
        self.repository.chunks = []
        status_code, _ = await asgi_request(
            "POST", f"/api/chat/sessions/{session_id}/messages",
            json.dumps({"question": "Question"}).encode(), {"content-type": "application/json"},
        )
        self.assertEqual(status_code, 409)
        self.assertEqual(self.repository.saved_turns, [])

        self.repository.chunks = [{
            "chunk_id": uuid4(), "content": "Evidence", "original_filename": "notes.txt",
            "page_number": None, "slide_number": None,
        }]
        self.provider.fail = True
        status_code, _ = await asgi_request(
            "POST", f"/api/chat/sessions/{session_id}/messages",
            json.dumps({"question": "Question"}).encode(), {"content-type": "application/json"},
        )
        self.assertEqual(status_code, 502)
        self.assertEqual(self.repository.saved_turns, [])

    async def test_other_users_cannot_read_or_send_to_session(self):
        session = self.repository.create_session(self.user_id, uuid4(), None)
        self.user = self.user.model_copy(update={"id": uuid4()})
        status_code, _ = await asgi_request(
            "GET", f"/api/chat/sessions/{session['id']}/messages"
        )
        self.assertEqual(status_code, 404)


if __name__ == "__main__":
    unittest.main()
