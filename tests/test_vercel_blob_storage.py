import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from vercel import blob

from backend.app.storage.vercel_blob import StorageFileNotFoundError, VercelBlobStorage


class VercelBlobStorageTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.storage = VercelBlobStorage()

    async def test_put_uses_private_store_and_returns_the_server_path(self) -> None:
        result = SimpleNamespace(pathname="users/user-id/documents/document-id/file.pdf")
        with patch("backend.app.storage.vercel_blob.blob.put_blob", new=AsyncMock(return_value=result)) as put:
            pathname = await self.storage.put("safe/path.pdf", b"%PDF", "application/pdf")

        self.assertEqual(pathname, result.pathname)
        put.assert_awaited_once_with(
            "safe/path.pdf",
            b"%PDF",
            access="private",
            content_length=4,
            content_type="application/pdf",
        )

    async def test_get_returns_content_and_maps_missing_private_blob(self) -> None:
        result = SimpleNamespace(
            body=b"study notes",
            metadata=SimpleNamespace(content_type="text/plain; charset=utf-8"),
        )
        with patch("backend.app.storage.vercel_blob.blob.get_blob", new=AsyncMock(return_value=result)) as get:
            self.assertEqual(
                await self.storage.get("users/user-id/documents/document-id/notes.txt"),
                (b"study notes", "text/plain; charset=utf-8"),
            )
        get.assert_awaited_once_with("users/user-id/documents/document-id/notes.txt", access="private")

        with patch(
            "backend.app.storage.vercel_blob.blob.get_blob",
            new=AsyncMock(side_effect=blob.BlobNotFoundError("missing")),
        ):
            with self.assertRaises(StorageFileNotFoundError):
                await self.storage.get("missing.pdf")

    async def test_delete_is_idempotent_when_blob_is_already_gone(self) -> None:
        with patch(
            "backend.app.storage.vercel_blob.blob.delete_blob",
            new=AsyncMock(side_effect=blob.BlobNotFoundError("missing")),
        ) as delete:
            await self.storage.delete("missing.pdf")
        delete.assert_awaited_once_with("missing.pdf")


if __name__ == "__main__":
    unittest.main()
