import io
import json
import unittest
import zipfile
from datetime import datetime, timezone
from unittest.mock import patch
from uuid import UUID, uuid4

from fastapi import HTTPException

from backend.app.auth.routes import PublicUser, current_user
from backend.app.documents.routes import (
    get_document_embedder,
    get_document_repository,
    get_document_storage,
)
from backend.app.main import app
from backend.app.processing.extraction import TextSection


class FakeDocumentRepository:
    def __init__(self) -> None:
        self.documents: dict[UUID, dict] = {}
        self.chunks: dict[UUID, list] = {}
        self.fail_cleanup_update = False

    def create_document(
        self,
        document_id: UUID,
        user_id: UUID,
        filename: str,
        file_format: str,
        storage_key: str,
        size_bytes: int,
    ) -> dict:
        row = {
            "id": document_id,
            "user_id": user_id,
            "original_filename": filename,
            "file_format": file_format,
            "storage_key": storage_key,
            "size_bytes": size_bytes,
            "status": "uploaded",
            "error_message": None,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "deleted_at": None,
        }
        self.documents[document_id] = row
        return row

    def list_documents(self, user_id: UUID) -> list[dict]:
        return [
            row.copy()
            for row in self.documents.values()
            if row["user_id"] == user_id and row["status"] != "deleted"
        ]

    def get_document(self, user_id: UUID, document_id: UUID) -> dict | None:
        row = self.documents.get(document_id)
        return row.copy() if row and row["user_id"] == user_id else None

    def begin_processing(self, user_id: UUID, document_id: UUID) -> tuple[dict, bool] | None:
        row = self.documents.get(document_id)
        if row is None or row["user_id"] != user_id or row["status"] in {"deleting", "deleted"}:
            return None
        if row["status"] not in {"uploaded", "failed"}:
            return row.copy(), False
        row["status"] = "processing"
        row["error_message"] = None
        return row.copy(), True

    def replace_chunks_and_mark_chunked(self, user_id: UUID, document_id: UUID, chunks) -> bool:
        row = self.documents.get(document_id)
        if row is None or row["user_id"] != user_id or row["status"] != "processing":
            return False
        self.chunks[document_id] = list(chunks)
        row["status"] = "chunked"
        row["error_message"] = None
        return True

    def fail_processing(self, user_id: UUID, document_id: UUID, message: str) -> None:
        row = self.documents.get(document_id)
        if row and row["user_id"] == user_id and row["status"] in {"processing", "chunked"}:
            row["status"] = "failed"
            row["error_message"] = message

    def save_embeddings_and_mark_ready(
        self, user_id: UUID, document_id: UUID, embeddings: list[list[float]]
    ) -> bool:
        row = self.documents.get(document_id)
        if row is None or row["user_id"] != user_id or row["status"] != "chunked":
            return False
        if len(self.chunks.get(document_id, [])) != len(embeddings):
            raise RuntimeError("Embedding count mismatch")
        row["status"] = "ready"
        return True

    def begin_delete(self, user_id: UUID, document_id: UUID) -> dict | None:
        row = self.documents.get(document_id)
        if row is None or row["user_id"] != user_id:
            return None
        if row["status"] != "deleted":
            row["status"] = "deleting"
            row["deleted_at"] = row["deleted_at"] or datetime.now(timezone.utc)
            row["error_message"] = None
        return {key: row[key] for key in ("id", "storage_key", "status")}

    def finish_delete(self, user_id: UUID, document_id: UUID) -> None:
        row = self.documents[document_id]
        if row["user_id"] == user_id and row["status"] == "deleting":
            row["status"] = "deleted"
            row["error_message"] = None

    def note_delete_failure(self, user_id: UUID, document_id: UUID) -> None:
        if self.fail_cleanup_update:
            raise RuntimeError("Database is unavailable")
        row = self.documents[document_id]
        if row["user_id"] == user_id and row["status"] == "deleting":
            row["error_message"] = "Storage cleanup pending"


class FakeDocumentStorage:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}
        self.fail_delete = False

    async def put(self, pathname: str, content: bytes, content_type: str) -> str:
        self.objects[pathname] = (content, content_type)
        return pathname

    async def get(self, pathname: str) -> tuple[bytes, str | None]:
        if pathname not in self.objects:
            from backend.app.storage.vercel_blob import StorageFileNotFoundError

            raise StorageFileNotFoundError
        return self.objects[pathname]

    async def delete(self, pathname: str) -> None:
        if self.fail_delete:
            raise RuntimeError("Storage is unavailable")
        self.objects.pop(pathname, None)


class FakeDocumentEmbedder:
    def __init__(self) -> None:
        self.fail = False

    def embed_passages(self, passages: list[str]) -> list[list[float]]:
        if self.fail:
            raise RuntimeError("embedding is unavailable")
        return [[0.0] * 384 for _ in passages]


def make_pdf_upload(filename: str = "lecture.pdf", content: bytes = b"%PDF-1.7\nexample") -> tuple[bytes, dict]:
    boundary = "memo-card-upload-boundary"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        "Content-Type: application/pdf\r\n\r\n"
    ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
    return body, {"content-type": f"multipart/form-data; boundary={boundary}"}


async def asgi_request(
    method: str,
    path: str,
    body: bytes = b"",
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[bytes, bytes], bytes]:
    request_headers = [(b"host", b"testserver"), (b"accept", b"application/json")]
    request_headers.extend((key.lower().encode(), value.encode()) for key, value in (headers or {}).items())
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
        "headers": request_headers,
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "state": {},
    }
    received = False
    events: list[dict] = []

    async def receive() -> dict:
        nonlocal received
        if received:
            return {"type": "http.disconnect"}
        received = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(event: dict) -> None:
        events.append(event)

    await app(scope, receive, send)
    status_code = next(event["status"] for event in events if event["type"] == "http.response.start")
    response_headers = dict(next(event["headers"] for event in events if event["type"] == "http.response.start"))
    response_body = b"".join(event.get("body", b"") for event in events if event["type"] == "http.response.body")
    return status_code, response_headers, response_body


class DocumentApiTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.user_id = uuid4()
        self.user = PublicUser(
            id=self.user_id,
            email="student@example.edu",
            display_name="Student",
            timezone="Asia/Kuala_Lumpur",
            created_at=datetime.now(timezone.utc),
        )
        self.repository = FakeDocumentRepository()
        self.storage = FakeDocumentStorage()
        self.embedder = FakeDocumentEmbedder()
        self.authenticated = True

        def get_user() -> PublicUser:
            if not self.authenticated:
                raise HTTPException(status_code=401, detail="Not authenticated")
            return self.user

        app.dependency_overrides[current_user] = get_user
        app.dependency_overrides[get_document_repository] = lambda: self.repository
        app.dependency_overrides[get_document_storage] = lambda: self.storage
        app.dependency_overrides[get_document_embedder] = lambda: self.embedder

    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    async def test_upload_lists_and_downloads_private_document(self) -> None:
        body, headers = make_pdf_upload("课程讲义.pdf")
        status_code, _, response_body = await asgi_request("POST", "/api/documents", body, headers)

        self.assertEqual(status_code, 201)
        response = json.loads(response_body)
        self.assertEqual(response["original_filename"], "课程讲义.pdf")
        self.assertEqual(response["file_format"], "pdf")
        self.assertEqual(response["status"], "uploaded")
        saved = self.repository.documents[UUID(response["id"])]
        self.assertTrue(saved["storage_key"].startswith(f"users/{self.user_id}/documents/"))
        self.assertEqual(self.storage.objects[saved["storage_key"]][0], b"%PDF-1.7\nexample")

        status_code, _, list_body = await asgi_request("GET", "/api/documents")
        self.assertEqual(status_code, 200)
        self.assertEqual(len(json.loads(list_body)), 1)

        status_code, download_headers, download_body = await asgi_request(
            "GET", f"/api/documents/{response['id']}/file"
        )
        self.assertEqual(status_code, 200)
        self.assertEqual(download_body, b"%PDF-1.7\nexample")
        self.assertIn(b"private, no-store", download_headers[b"cache-control"])
        self.assertIn(b"nosniff", download_headers[b"x-content-type-options"])

    async def test_txt_processing_saves_owned_chunks_and_is_idempotent(self) -> None:
        body, headers = make_pdf_upload("lecture.txt", "记忆间隔 helps long-term learning.\nReview often.".encode())
        status_code, _, upload_body = await asgi_request("POST", "/api/documents", body, headers)
        self.assertEqual(status_code, 201)
        document_id = UUID(json.loads(upload_body)["id"])

        status_code, _, processed_body = await asgi_request(
            "POST", f"/api/documents/{document_id}/process"
        )
        self.assertEqual(status_code, 200)
        self.assertEqual(json.loads(processed_body)["status"], "ready")
        chunks = self.repository.chunks[document_id]
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].content, "记忆间隔 helps long-term learning.\nReview often.")
        self.assertIsNone(chunks[0].page_number)
        self.assertIsNone(chunks[0].slide_number)

        status_code, _, _ = await asgi_request("POST", f"/api/documents/{document_id}/process")
        self.assertEqual(status_code, 200)
        self.assertEqual(len(self.repository.chunks[document_id]), 1)

    async def test_unreadable_pdf_is_marked_failed_with_explanation(self) -> None:
        body, headers = make_pdf_upload("scan.pdf", b"%PDF-1.7\nnot a readable PDF")
        status_code, _, upload_body = await asgi_request("POST", "/api/documents", body, headers)
        self.assertEqual(status_code, 201)
        document_id = UUID(json.loads(upload_body)["id"])

        status_code, _, processed_body = await asgi_request(
            "POST", f"/api/documents/{document_id}/process"
        )
        response = json.loads(processed_body)
        self.assertEqual(status_code, 200)
        self.assertEqual(response["status"], "failed")
        self.assertTrue(response["error_message"])

    async def test_failed_document_can_retry_processing(self) -> None:
        body, headers = make_pdf_upload("retry.pdf", b"%PDF-1.7\ninvalid")
        status_code, _, upload_body = await asgi_request("POST", "/api/documents", body, headers)
        self.assertEqual(status_code, 201)
        document_id = UUID(json.loads(upload_body)["id"])

        _, _, failed_body = await asgi_request("POST", f"/api/documents/{document_id}/process")
        self.assertEqual(json.loads(failed_body)["status"], "failed")

        with patch(
            "backend.app.documents.routes.extract_document",
            return_value=[TextSection("Recovered text", page_number=1)],
        ):
            status_code, _, retried_body = await asgi_request(
                "POST", f"/api/documents/{document_id}/process"
            )
        response = json.loads(retried_body)
        self.assertEqual(status_code, 200)
        self.assertEqual(response["status"], "ready")
        self.assertEqual(self.repository.chunks[document_id][0].content, "Recovered text")

    async def test_embedding_failure_does_not_mark_document_ready_and_can_retry(self) -> None:
        body, headers = make_pdf_upload("retry-index.txt", b"Vector indexing retry.")
        status_code, _, upload_body = await asgi_request("POST", "/api/documents", body, headers)
        self.assertEqual(status_code, 201)
        document_id = UUID(json.loads(upload_body)["id"])

        self.embedder.fail = True
        _, _, failed_body = await asgi_request("POST", f"/api/documents/{document_id}/process")
        self.assertEqual(json.loads(failed_body)["status"], "failed")
        self.assertEqual(
            json.loads(failed_body)["error_message"],
            "The text was extracted but could not be indexed. Retry processing later.",
        )

        self.embedder.fail = False
        _, _, retried_body = await asgi_request("POST", f"/api/documents/{document_id}/process")
        self.assertEqual(json.loads(retried_body)["status"], "ready")

    async def test_processing_endpoint_rejects_other_users(self) -> None:
        row = self.repository.create_document(
            uuid4(), uuid4(), "private.txt", "txt", "other/private.txt", 4
        )
        status_code, _, _ = await asgi_request("POST", f"/api/documents/{row['id']}/process")
        self.assertEqual(status_code, 404)

    async def test_upload_rejects_unsupported_type_invalid_signature_and_oversize(self) -> None:
        body, headers = make_pdf_upload("legacy.ppt", b"not a presentation")
        status_code, _, _ = await asgi_request("POST", "/api/documents", body, headers)
        self.assertEqual(status_code, 415)
        self.assertEqual(self.storage.objects, {})

        body, headers = make_pdf_upload("broken.pdf", b"not a PDF")
        status_code, _, _ = await asgi_request("POST", "/api/documents", body, headers)
        self.assertEqual(status_code, 422)
        self.assertEqual(self.storage.objects, {})

        body, headers = make_pdf_upload("large.pdf", b"%PDF-" + b"x" * (4 * 1024 * 1024))
        status_code, _, _ = await asgi_request("POST", "/api/documents", body, headers)
        self.assertEqual(status_code, 413)
        self.assertEqual(self.storage.objects, {})

    async def test_txt_and_pptx_signatures_are_checked(self) -> None:
        text_body, text_headers = make_pdf_upload("notes.txt", "学习笔记".encode("utf-8"))
        status_code, _, text_response = await asgi_request("POST", "/api/documents", text_body, text_headers)
        self.assertEqual(status_code, 201)
        self.assertEqual(json.loads(text_response)["file_format"], "txt")

        presentation = io.BytesIO()
        with zipfile.ZipFile(presentation, "w") as archive:
            archive.writestr("ppt/presentation.xml", "<presentation/>")
        pptx_body, pptx_headers = make_pdf_upload("slides.pptx", presentation.getvalue())
        status_code, _, pptx_response = await asgi_request("POST", "/api/documents", pptx_body, pptx_headers)
        self.assertEqual(status_code, 201)
        self.assertEqual(json.loads(pptx_response)["file_format"], "pptx")

    async def test_unauthenticated_and_cross_user_requests_are_rejected(self) -> None:
        self.authenticated = False
        status_code, _, _ = await asgi_request("GET", "/api/documents")
        self.assertEqual(status_code, 401)

        self.authenticated = True
        other_user_document = self.repository.create_document(
            uuid4(), uuid4(), "private.pdf", "pdf", "other/private.pdf", 10
        )
        status_code, _, _ = await asgi_request(
            "GET", f"/api/documents/{other_user_document['id']}/file"
        )
        self.assertEqual(status_code, 404)

    async def test_soft_delete_hides_document_and_retries_failed_blob_cleanup(self) -> None:
        body, headers = make_pdf_upload()
        status_code, _, response_body = await asgi_request("POST", "/api/documents", body, headers)
        self.assertEqual(status_code, 201)
        document_id = UUID(json.loads(response_body)["id"])
        self.storage.fail_delete = True

        status_code, _, _ = await asgi_request("DELETE", f"/api/documents/{document_id}")
        self.assertEqual(status_code, 503)
        self.assertEqual(self.repository.documents[document_id]["status"], "deleting")
        self.assertEqual(self.repository.documents[document_id]["error_message"], "Storage cleanup pending")
        status_code, _, list_body = await asgi_request("GET", "/api/documents")
        self.assertEqual(status_code, 200)
        self.assertEqual(json.loads(list_body)[0]["status"], "deleting")

        self.storage.fail_delete = False
        status_code, _, _ = await asgi_request("DELETE", f"/api/documents/{document_id}")
        self.assertEqual(status_code, 204)
        self.assertEqual(self.repository.documents[document_id]["status"], "deleted")
        self.assertEqual(self.storage.objects, {})
        status_code, _, list_body = await asgi_request("GET", "/api/documents")
        self.assertEqual(status_code, 200)
        self.assertEqual(json.loads(list_body), [])


if __name__ == "__main__":
    unittest.main()
