import io
import logging
import re
import zipfile
from datetime import datetime
from pathlib import PurePosixPath
from typing import Annotated
from urllib.parse import quote
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from backend.app.auth.routes import PublicUser, current_user
from backend.app.storage.vercel_blob import (
    DocumentStorage,
    StorageFileNotFoundError,
    VercelBlobStorage,
)
from backend.app.documents.repository import PostgresDocumentRepository
from backend.app.processing.chunking import build_document_chunks
from backend.app.processing.embeddings import TextEmbedder
from backend.app.processing.extraction import DocumentProcessingError, extract_document


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])
MAX_UPLOAD_BYTES = 15 * 1024 * 1024
FILE_TYPES = {
    ".pdf": ("pdf", "application/pdf"),
    ".txt": ("txt", "text/plain; charset=utf-8"),
    ".pptx": (
        "pptx",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ),
}
DOWNLOAD_MEDIA_TYPES = {
    **{extension[1:]: file_type[1] for extension, file_type in FILE_TYPES.items()},
    "ppt": "application/vnd.ms-powerpoint",
}
ALLOWED_FILENAME = re.compile(r"^[^\x00-\x1f\x7f]+$")


class DocumentResponse(BaseModel):
    id: UUID
    original_filename: str
    file_format: str
    size_bytes: int
    status: str
    error_message: str | None
    created_at: datetime
    deleted_at: datetime | None


def get_document_repository() -> PostgresDocumentRepository:
    return PostgresDocumentRepository()


def get_document_storage() -> DocumentStorage:
    return VercelBlobStorage()


def get_document_embedder() -> TextEmbedder:
    return TextEmbedder()


Repository = Annotated[PostgresDocumentRepository, Depends(get_document_repository)]
Storage = Annotated[DocumentStorage, Depends(get_document_storage)]
Embedder = Annotated[TextEmbedder, Depends(get_document_embedder)]
AuthenticatedUser = Annotated[PublicUser, Depends(current_user)]


def _filename_and_type(upload: UploadFile) -> tuple[str, str, str]:
    raw_filename = (upload.filename or "").replace("\\", "/")
    filename = PurePosixPath(raw_filename).name.strip()
    if not filename or len(filename) > 255 or ALLOWED_FILENAME.fullmatch(filename) is None:
        raise HTTPException(status_code=422, detail="The filename is invalid")

    file_type = FILE_TYPES.get(PurePosixPath(filename).suffix.lower())
    if file_type is None:
        raise HTTPException(status_code=415, detail="Upload a PDF, UTF-8 TXT, or PPTX file")
    file_format, media_type = file_type
    return filename, file_format, media_type


def _validate_file_content(file_format: str, content: bytes) -> None:
    if not content:
        raise HTTPException(status_code=422, detail="The file is empty")

    if file_format == "pdf":
        if b"%PDF-" not in content[:1024]:
            raise HTTPException(status_code=422, detail="The file does not contain a valid PDF header")
        return

    if file_format == "txt":
        if b"\x00" in content:
            raise HTTPException(status_code=422, detail="TXT files must be UTF-8 text")
        try:
            content.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise HTTPException(status_code=422, detail="TXT files must be UTF-8 encoded") from error
        return

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = archive.namelist()
    except (OSError, zipfile.BadZipFile) as error:
        raise HTTPException(status_code=422, detail="The file is not a valid PPTX presentation") from error
    if len(names) > 10_000 or "ppt/presentation.xml" not in names:
        raise HTTPException(status_code=422, detail="The file is not a valid PPTX presentation")


@router.get("", response_model=list[DocumentResponse])
async def list_documents(user: AuthenticatedUser, repository: Repository) -> list[dict]:
    return await run_in_threadpool(repository.list_documents, user.id)


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    user: AuthenticatedUser,
    repository: Repository,
    storage: Storage,
    file: UploadFile = File(...),
) -> dict:
    filename, file_format, media_type = _filename_and_type(file)
    if file.size is not None and file.size > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Files must be 15 MiB or smaller")

    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Files must be 15 MiB or smaller")
    _validate_file_content(file_format, content)

    document_id = uuid4()
    storage_key = f"users/{user.id}/documents/{document_id}/{uuid4().hex}.{file_format}"
    try:
        stored_key = await storage.put(storage_key, content, media_type)
    except Exception as error:
        logger.warning("Private document upload failed (%s)", type(error).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document storage is temporarily unavailable",
        ) from error

    try:
        return await run_in_threadpool(
            repository.create_document,
            document_id,
            user.id,
            filename,
            file_format,
            stored_key,
            len(content),
        )
    except Exception as error:
        try:
            await storage.delete(stored_key)
        except Exception as cleanup_error:
            logger.warning(
                "Document metadata failed; blob cleanup needs attention (%s)",
                type(cleanup_error).__name__,
            )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The upload could not be saved. Please try again",
        ) from error


@router.get("/{document_id}/file")
async def download_document(
    document_id: UUID,
    user: AuthenticatedUser,
    repository: Repository,
    storage: Storage,
) -> Response:
    document = await run_in_threadpool(repository.get_document, user.id, document_id)
    if document is None or document["status"] in {"deleting", "deleted"}:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        content, stored_media_type = await storage.get(document["storage_key"])
    except StorageFileNotFoundError as error:
        raise HTTPException(status_code=404, detail="Document file not found") from error
    except Exception as error:
        logger.warning("Private document download failed (%s)", type(error).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document storage is temporarily unavailable",
        ) from error

    canonical_media_type = DOWNLOAD_MEDIA_TYPES[document["file_format"]]
    filename = document["original_filename"].replace("\r", " ").replace("\n", " ")
    return Response(
        content=content,
        media_type=stored_media_type or canonical_media_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename, safe='')}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


async def _failed_processing_response(
    repository: PostgresDocumentRepository,
    user_id: UUID,
    document_id: UUID,
    message: str,
) -> dict:
    try:
        await run_in_threadpool(repository.fail_processing, user_id, document_id, message)
        document = await run_in_threadpool(repository.get_document, user_id, document_id)
    except Exception as error:
        logger.warning("Document processing status could not be saved (%s)", type(error).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The processing result could not be saved. Please retry later",
        ) from error
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@router.post("/{document_id}/process", response_model=DocumentResponse)
async def process_document(
    document_id: UUID,
    user: AuthenticatedUser,
    repository: Repository,
    storage: Storage,
    embedder: Embedder,
) -> dict:
    try:
        claim = await run_in_threadpool(repository.begin_processing, user.id, document_id)
    except Exception as error:
        logger.warning("Document processing could not start (%s)", type(error).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document processing is temporarily unavailable",
        ) from error
    if claim is None:
        raise HTTPException(status_code=404, detail="Document not found")

    document, claimed = claim
    if not claimed:
        return document

    try:
        content, _ = await storage.get(document["storage_key"])
    except StorageFileNotFoundError:
        return await _failed_processing_response(
            repository, user.id, document_id, "The private file is missing. Re-upload this document."
        )
    except Exception as error:
        logger.warning("Private document read for processing failed (%s)", type(error).__name__)
        return await _failed_processing_response(
            repository, user.id, document_id, "The private file could not be read. Retry processing later."
        )

    if len(content) > MAX_UPLOAD_BYTES or len(content) != document["size_bytes"]:
        return await _failed_processing_response(
            repository,
            user.id,
            document_id,
            "The stored file does not match its upload metadata. Re-upload this document.",
        )

    try:
        sections = await run_in_threadpool(extract_document, document["file_format"], content)
        chunks = await run_in_threadpool(build_document_chunks, document_id, sections)
        if not chunks:
            raise DocumentProcessingError("No readable text chunks were produced from this document.")
    except DocumentProcessingError as error:
        return await _failed_processing_response(repository, user.id, document_id, str(error))
    except Exception as error:
        logger.warning("Document text extraction failed (%s)", type(error).__name__)
        return await _failed_processing_response(
            repository, user.id, document_id, "The document could not be processed. Check the file and retry."
        )

    try:
        saved = await run_in_threadpool(
            repository.replace_chunks_and_mark_chunked, user.id, document_id, chunks
        )
    except Exception as error:
        logger.warning("Document chunks could not be saved (%s)", type(error).__name__)
        return await _failed_processing_response(
            repository, user.id, document_id, "The extracted text could not be saved. Retry processing."
        )
    if not saved:
        current = await run_in_threadpool(repository.get_document, user.id, document_id)
        if current is None:
            raise HTTPException(status_code=404, detail="Document not found")
        return current

    try:
        embeddings = await run_in_threadpool(
            embedder.embed_passages, [chunk.content for chunk in chunks]
        )
        if len(embeddings) != len(chunks) or any(len(vector) != 384 for vector in embeddings):
            raise RuntimeError("The embedding model returned an unexpected vector shape")
        indexed = await run_in_threadpool(
            repository.save_embeddings_and_mark_ready, user.id, document_id, embeddings
        )
    except Exception as error:
        # The class name alone cannot distinguish a model-registration conflict from a
        # download or pgvector failure, so the traceback (which carries the exception
        # message) is logged alongside it for diagnosis.
        logger.warning("Document vector indexing failed (%s)", type(error).__name__, exc_info=True)
        return await _failed_processing_response(
            repository,
            user.id,
            document_id,
            "The text was extracted but could not be indexed. Retry processing later.",
        )
    if not indexed:
        current = await run_in_threadpool(repository.get_document, user.id, document_id)
        if current is None:
            raise HTTPException(status_code=404, detail="Document not found")
        return current

    processed = await run_in_threadpool(repository.get_document, user.id, document_id)
    if processed is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return processed


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: UUID,
    user: AuthenticatedUser,
    repository: Repository,
    storage: Storage,
) -> Response:
    document = await run_in_threadpool(repository.begin_delete, user.id, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if document["status"] == "deleted":
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    try:
        await storage.delete(document["storage_key"])
    except Exception as error:
        await run_in_threadpool(repository.note_delete_failure, user.id, document_id)
        logger.warning("Private document cleanup is pending (%s)", type(error).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Deletion is pending. Retry cleanup from the document list",
        ) from error

    await run_in_threadpool(repository.finish_delete, user.id, document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
