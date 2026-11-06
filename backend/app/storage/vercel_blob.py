from typing import Protocol

from vercel import blob


class StorageFileNotFoundError(Exception):
    """Raised when a document's private blob no longer exists."""


class DocumentStorage(Protocol):
    async def put(self, pathname: str, content: bytes, content_type: str) -> str: ...

    async def get(self, pathname: str) -> tuple[bytes, str | None]: ...

    async def delete(self, pathname: str) -> None: ...


class VercelBlobStorage:
    """Keep user documents in private Blob storage, never in function-local disk."""

    async def put(self, pathname: str, content: bytes, content_type: str) -> str:
        uploaded = await blob.put_blob(
            pathname,
            content,
            access="private",
            content_length=len(content),
            content_type=content_type,
        )
        return uploaded.pathname

    async def get(self, pathname: str) -> tuple[bytes, str | None]:
        try:
            downloaded = await blob.get_blob(pathname, access="private")
        except blob.BlobNotFoundError as error:
            raise StorageFileNotFoundError from error
        return downloaded.body, downloaded.metadata.content_type

    async def delete(self, pathname: str) -> None:
        try:
            await blob.delete_blob(pathname)
        except blob.BlobNotFoundError:
            # A retry after a partial delete is safe: absence is the desired state.
            return
