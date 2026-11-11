import json
import unittest
from datetime import date, datetime, timezone
from uuid import uuid4

from backend.app.analytics.routes import get_analytics_repository
from backend.app.auth.routes import PublicUser, current_user
from backend.app.main import app


class FakeAnalyticsRepository:
    def __init__(self, user_id):
        self.user_id = user_id
        self.requested_timezone = None
        self.fail = False

    def get_summary(self, user_id, timezone_name):
        if self.fail:
            raise RuntimeError("database unavailable")
        self.requested_timezone = timezone_name
        return {
            "reviewed_total": 12,
            "correct_rate": 0.75,
            "streak_days": 3,
            "mastery": {"new": 2, "learning": 5, "mastered": 9},
            "upcoming": [{"date": date(2026, 11, 12), "count": 4}],
        }


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


class AnalyticsApiTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.user_id = uuid4()
        self.user = PublicUser(
            id=self.user_id, email="student@example.edu", display_name="Student",
            timezone="Asia/Kuala_Lumpur", created_at=datetime.now(timezone.utc),
        )
        self.repository = FakeAnalyticsRepository(self.user_id)
        app.dependency_overrides[current_user] = lambda: self.user
        app.dependency_overrides[get_analytics_repository] = lambda: self.repository

    def tearDown(self):
        app.dependency_overrides.clear()

    async def test_summary_is_scoped_to_the_account_timezone(self):
        status_code, body = await asgi_request("GET", "/api/analytics/summary")
        self.assertEqual(status_code, 200)
        payload = json.loads(body)
        self.assertEqual(payload["timezone"], "Asia/Kuala_Lumpur")
        self.assertEqual(self.repository.requested_timezone, "Asia/Kuala_Lumpur")
        self.assertEqual(payload["mastery"], {"new": 2, "learning": 5, "mastered": 9})
        self.assertEqual(payload["upcoming"], [{"date": "2026-11-12", "count": 4}])
        self.assertAlmostEqual(payload["correct_rate"], 0.75)

    async def test_invalid_timezone_is_reported_as_a_configuration_error(self):
        self.user = self.user.model_copy(update={"timezone": "Mars/Olympus"})
        status_code, _ = await asgi_request("GET", "/api/analytics/summary")
        self.assertEqual(status_code, 500)

    async def test_repository_failure_returns_a_retryable_error(self):
        self.repository.fail = True
        status_code, _ = await asgi_request("GET", "/api/analytics/summary")
        self.assertEqual(status_code, 503)


if __name__ == "__main__":
    unittest.main()
