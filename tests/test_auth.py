import os
import asyncio
import json
import unittest
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from unittest.mock import patch
from uuid import UUID, uuid4

from fastapi import HTTPException, Response

from backend.app.auth.repository import DuplicateEmailError
from backend.app.auth.routes import (
    SESSION_COOKIE,
    Credentials,
    ProfileUpdate,
    Registration,
    current_user,
    get_profile,
    get_repository,
    login,
    logout,
    register,
    update_profile,
)
from backend.app.auth.security import hash_password, hash_session_token, verify_password
from backend.app.main import app


class FakeAuthRepository:
    def __init__(self) -> None:
        self.users: dict[str, dict] = {}
        self.sessions: dict[str, dict] = {}

    def create_user(
        self,
        email: str,
        encoded_password: str,
        display_name: str,
        timezone_name: str = "UTC",
    ) -> dict:
        if email in self.users:
            raise DuplicateEmailError
        user = {
            "id": uuid4(),
            "email": email,
            "password_hash": encoded_password,
            "display_name": display_name,
            "timezone": timezone_name,
            "created_at": datetime.now(timezone.utc),
        }
        self.users[email] = user
        return user

    def get_user_by_email(self, email: str) -> dict | None:
        return self.users.get(email)

    def create_session(self, user_id: UUID, token_hash: str) -> datetime:
        expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        self.sessions[token_hash] = {"user_id": user_id, "expires_at": expires_at, "revoked": False}
        return expires_at

    def get_user_for_session(self, token_hash: str) -> dict | None:
        session = self.sessions.get(token_hash)
        if not session or session["revoked"] or session["expires_at"] <= datetime.now(timezone.utc):
            return None
        return next((u for u in self.users.values() if u["id"] == session["user_id"]), None)

    def revoke_session(self, token_hash: str) -> None:
        if token_hash in self.sessions:
            self.sessions[token_hash]["revoked"] = True

    def update_profile(
        self,
        user_id: UUID,
        display_name: str | None,
        timezone_name: str | None,
    ) -> dict | None:
        user = next((u for u in self.users.values() if u["id"] == user_id), None)
        if user is not None:
            if display_name is not None:
                user["display_name"] = display_name
            if timezone_name is not None:
                user["timezone"] = timezone_name
        return user


def cookie_value(response: Response) -> str:
    cookie = SimpleCookie()
    cookie.load(response.headers["set-cookie"])
    return cookie[SESSION_COOKIE].value


class AuthenticationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = FakeAuthRepository()
        self.registration = Registration(
            email="  Student@Example.edu ",
            password="Correct-Horse-Battery-17",
            display_name="  Student  ",
        )

    def test_registration_creates_user_and_secure_cookie(self) -> None:
        response = Response()
        with patch.dict(os.environ, {"APP_ENV": "production"}):
            user = register(self.registration, response, self.repository)
        self.assertEqual(user.email, "student@example.edu")
        self.assertEqual(user.display_name, "Student")
        self.assertEqual(user.timezone, "UTC")
        cookie_header = response.headers["set-cookie"].lower()
        self.assertIn("httponly", cookie_header)
        self.assertIn("secure", cookie_header)
        self.assertIn("samesite=lax", cookie_header)
        token = cookie_value(response)
        self.assertNotIn(token, self.repository.sessions)
        self.assertIn(hash_session_token(token), self.repository.sessions)

    def test_duplicate_registration_returns_conflict(self) -> None:
        register(self.registration, Response(), self.repository)
        with self.assertRaises(HTTPException) as raised:
            register(self.registration, Response(), self.repository)
        self.assertEqual(raised.exception.status_code, 409)

    def test_login_profile_update_and_logout(self) -> None:
        user = register(self.registration, Response(), self.repository)
        login_response = Response()
        logged_in = login(
            Credentials(email="STUDENT@example.edu", password=self.registration.password),
            login_response,
            self.repository,
        )
        self.assertEqual(logged_in.id, user.id)
        token = cookie_value(login_response)

        current = current_user(self.repository, token)
        self.assertEqual(get_profile(current).id, user.id)

        updated = update_profile(ProfileUpdate(display_name="New Name"), current, self.repository)
        self.assertEqual(updated.display_name, "New Name")

        timezone_updated = update_profile(
            ProfileUpdate(timezone="Asia/Kuala_Lumpur"),
            current,
            self.repository,
        )
        self.assertEqual(timezone_updated.timezone, "Asia/Kuala_Lumpur")

        with patch.dict(os.environ, {"APP_ENV": "development"}):
            logout_response = Response()
            logout(logout_response, self.repository, token)
        self.assertIn("max-age=0", logout_response.headers["set-cookie"].lower())
        self.assertNotIn("; secure", logout_response.headers["set-cookie"].lower())
        with self.assertRaises(HTTPException) as raised:
            current_user(self.repository, token)
        self.assertEqual(raised.exception.status_code, 401)

    def test_invalid_login_and_missing_session_are_rejected(self) -> None:
        register(self.registration, Response(), self.repository)
        with self.assertRaises(HTTPException) as raised:
            login(Credentials(email="student@example.edu", password="Wrong-Password-123"), Response(), self.repository)
        self.assertEqual(raised.exception.status_code, 401)
        with self.assertRaises(HTTPException) as raised:
            login(Credentials(email="missing@example.edu", password="Wrong-Password-123"), Response(), self.repository)
        self.assertEqual(raised.exception.status_code, 401)
        with self.assertRaises(HTTPException) as raised:
            current_user(self.repository, None)
        self.assertEqual(raised.exception.status_code, 401)

    def test_password_hashing_and_api_routes(self) -> None:
        encoded = hash_password("Correct-Horse-Battery-17")
        self.assertTrue(verify_password("Correct-Horse-Battery-17", encoded))
        self.assertFalse(verify_password("incorrect", encoded))
        self.assertEqual(
            set(app.openapi()["paths"]),
            {
                "/api/auth/register",
                "/api/auth/login",
                "/api/auth/logout",
                "/api/auth/me",
                "/api/flashcards/{flashcard_id}/reviews",
            },
        )


async def asgi_request(method: str, path: str, body: dict | None = None, cookie: str | None = None):
    request_body = json.dumps(body or {}).encode("utf-8") if method in {"POST", "PATCH"} else b""
    headers = [(b"host", b"testserver"), (b"accept", b"application/json")]
    if method in {"POST", "PATCH"}:
        headers.append((b"content-type", b"application/json"))
    if cookie:
        headers.append((b"cookie", cookie.encode("latin-1")))

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "root_path": "",
        "headers": headers,
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "state": {},
    }
    received = False
    events: list[dict] = []

    async def receive() -> dict:
        nonlocal received
        if not received:
            received = True
            return {"type": "http.request", "body": request_body, "more_body": False}
        await asyncio.sleep(0)
        return {"type": "http.disconnect"}

    async def send(event: dict) -> None:
        events.append(event)

    await app(scope, receive, send)
    start = next(event for event in events if event["type"] == "http.response.start")
    content = b"".join(
        event.get("body", b"") for event in events if event["type"] == "http.response.body"
    )
    return start["status"], dict(start["headers"]), content


class AuthenticationHTTPTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.repository = FakeAuthRepository()
        self._old_environment = os.environ.get("APP_ENV")
        os.environ["APP_ENV"] = "development"
        app.dependency_overrides[get_repository] = lambda: self.repository

    async def asyncTearDown(self) -> None:
        app.dependency_overrides.pop(get_repository, None)
        if self._old_environment is None:
            os.environ.pop("APP_ENV", None)
        else:
            os.environ["APP_ENV"] = self._old_environment

    async def test_register_me_and_logout_over_http(self) -> None:
        status_code, headers, body = await asgi_request(
            "POST",
            "/api/auth/register",
            {"email": "Student@example.edu", "password": "Correct-Horse-Battery-17", "display_name": "Student"},
        )
        self.assertEqual(status_code, 201)
        self.assertEqual(json.loads(body)["email"], "student@example.edu")
        cookie_header = headers[b"set-cookie"].decode("latin-1")
        self.assertIn("httponly", cookie_header.lower())
        self.assertIn("samesite=lax", cookie_header.lower())
        self.assertNotIn("; secure", cookie_header.lower())
        cookie = SimpleCookie()
        cookie.load(cookie_header)
        session_cookie = f"{SESSION_COOKIE}={cookie[SESSION_COOKIE].value}"

        status_code, _, body = await asgi_request("GET", "/api/auth/me", cookie=session_cookie)
        self.assertEqual(status_code, 200)
        self.assertEqual(json.loads(body)["display_name"], "Student")

        status_code, headers, _ = await asgi_request("POST", "/api/auth/logout", cookie=session_cookie)
        self.assertEqual(status_code, 204)
        self.assertIn("max-age=0", headers[b"set-cookie"].decode("latin-1").lower())

        status_code, _, _ = await asgi_request("GET", "/api/auth/me", cookie=session_cookie)
        self.assertEqual(status_code, 401)


if __name__ == "__main__":
    unittest.main()
