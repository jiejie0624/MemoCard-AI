import asyncio
import json
import unittest
from datetime import date, datetime, timezone
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import HTTPException

from backend.app.auth.routes import PublicUser, current_user
from backend.app.calendar.routes import get_calendar_repository
from backend.app.dashboard.routes import get_dashboard_repository
from backend.app.main import app


class FakeCalendarRepository:
    def __init__(self, user_id):
        self.user_id = user_id
        self.day_count_args = None
        self.day_card_args = None
        self.document_id = uuid4()

    def get_summary(self, user_id, timezone_name):
        if user_id != self.user_id:
            raise AssertionError("Calendar query must use the authenticated user")
        return {
            "today": date(2026, 11, 10),
            "overdue_count": 2,
            "today_count": 3,
            "upcoming_count": 5,
            "next_review_at": datetime(2026, 11, 10, 16, tzinfo=timezone.utc),
        }

    def get_day_counts(self, user_id, timezone_name, start_date, end_date):
        self.day_count_args = (user_id, timezone_name, start_date, end_date)
        return [{"due_date": date(2026, 11, 12), "card_count": 4}]

    def get_day_cards(self, user_id, timezone_name, due_date):
        self.day_card_args = (user_id, timezone_name, due_date)
        return [{
            "id": uuid4(),
            "question": "What is spaced repetition?",
            "answer": "A planned review process.",
            "next_review_at": datetime(2026, 11, 12, tzinfo=timezone.utc),
            "sources": [{"id": self.document_id, "name": "lecture-notes.pdf"}],
        }]


async def asgi_request(path):
    parsed = urlsplit(path)
    events = []
    sent = False
    scope = {
        "type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1", "method": "GET", "scheme": "http", "path": parsed.path,
        "raw_path": parsed.path.encode(), "query_string": parsed.query.encode(), "root_path": "",
        "headers": [(b"host", b"testserver"), (b"accept", b"application/json")],
        "client": ("127.0.0.1", 12345), "server": ("testserver", 80), "state": {},
    }

    async def receive():
        nonlocal sent
        if sent:
            await asyncio.sleep(0)
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(event):
        events.append(event)

    await app(scope, receive, send)
    response = next(item for item in events if item["type"] == "http.response.start")
    body = b"".join(item.get("body", b"") for item in events if item["type"] == "http.response.body")
    return response["status"], json.loads(body) if body else None


class CalendarApiTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.user_id = uuid4()
        self.user = PublicUser(
            id=self.user_id, email="student@example.edu", display_name="Student",
            timezone="Asia/Kuala_Lumpur", created_at=datetime.now(timezone.utc),
        )
        self.repository = FakeCalendarRepository(self.user_id)
        self.authenticated = True

        def get_user():
            if not self.authenticated:
                raise HTTPException(status_code=401, detail="Not authenticated")
            return self.user

        app.dependency_overrides[current_user] = get_user
        app.dependency_overrides[get_calendar_repository] = lambda: self.repository
        app.dependency_overrides[get_dashboard_repository] = lambda: self.repository

    def tearDown(self):
        app.dependency_overrides.clear()

    async def test_summary_returns_timezone_aware_review_counts(self):
        status_code, body = await asgi_request("/api/dashboard/summary")
        self.assertEqual(status_code, 200)
        self.assertEqual(body["timezone"], "Asia/Kuala_Lumpur")
        self.assertEqual(body["today"], "2026-11-10")
        self.assertEqual(body["overdue_count"], 2)
        self.assertEqual(body["today_count"], 3)
        self.assertEqual(body["upcoming_count"], 5)

    async def test_calendar_fills_empty_dates_and_uses_profile_timezone(self):
        status_code, body = await asgi_request("/api/revisions?from=2026-11-10&to=2026-11-12")
        self.assertEqual(status_code, 200)
        self.assertEqual([day["count"] for day in body["days"]], [0, 0, 4])
        self.assertEqual(
            self.repository.day_count_args,
            (self.user_id, "Asia/Kuala_Lumpur", date(2026, 11, 10), date(2026, 11, 12)),
        )

    async def test_day_returns_only_the_authenticated_users_cards(self):
        status_code, body = await asgi_request("/api/revisions/day?date=2026-11-12")
        self.assertEqual(status_code, 200)
        self.assertEqual(body["cards"][0]["sources"], [{"id": str(self.repository.document_id), "name": "lecture-notes.pdf"}])
        self.assertEqual(
            self.repository.day_card_args,
            (self.user_id, "Asia/Kuala_Lumpur", date(2026, 11, 12)),
        )

    async def test_calendar_rejects_invalid_or_oversized_ranges(self):
        status_code, _ = await asgi_request("/api/revisions?from=2026-11-12&to=2026-11-10")
        self.assertEqual(status_code, 422)
        status_code, _ = await asgi_request("/api/revisions?from=2026-11-01&to=2026-12-13")
        self.assertEqual(status_code, 422)

    async def test_calendar_endpoints_require_authentication(self):
        self.authenticated = False
        status_code, _ = await asgi_request("/api/dashboard/summary")
        self.assertEqual(status_code, 401)


if __name__ == "__main__":
    unittest.main()
