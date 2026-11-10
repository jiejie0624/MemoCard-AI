"""Extract bounded, source-located text from supported study documents."""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass

from pypdf import PdfReader
from pptx import Presentation


MAX_DOCUMENT_PAGES = 500
MAX_EXTRACTED_CHARACTERS = 2_000_000
MAX_PPTX_ENTRIES = 10_000
MAX_PPTX_UNCOMPRESSED_BYTES = 64 * 1024 * 1024
MAX_PPTX_ENTRY_BYTES = 32 * 1024 * 1024
MAX_PPTX_COMPRESSION_RATIO = 1_000


class DocumentProcessingError(ValueError):
    """An expected, safe-to-show error while reading a user document."""


@dataclass(frozen=True)
class TextSection:
    text: str
    page_number: int | None = None
    slide_number: int | None = None


def _check_extracted_size(sections: list[TextSection]) -> None:
    if sum(len(section.text) for section in sections) > MAX_EXTRACTED_CHARACTERS:
        raise DocumentProcessingError(
            "The extracted text is too large to process. Split the file into smaller documents."
        )


def _extract_pdf(content: bytes) -> list[TextSection]:
    try:
        reader = PdfReader(io.BytesIO(content), strict=False)
        if reader.is_encrypted:
            raise DocumentProcessingError("Password-protected PDFs are not supported.")
        page_count = len(reader.pages)
        if page_count > MAX_DOCUMENT_PAGES:
            raise DocumentProcessingError("PDFs may contain at most 500 pages.")

        sections = []
        for page_number, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                sections.append(TextSection(text=text, page_number=page_number))
                _check_extracted_size(sections)
    except DocumentProcessingError:
        raise
    except Exception as error:
        raise DocumentProcessingError("The PDF could not be read. Check the file and try again.") from error

    if not sections:
        raise DocumentProcessingError(
            "No readable text was found. Scanned PDFs need OCR, which is not available yet."
        )
    return sections


def _check_pptx_archive(content: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_PPTX_ENTRIES or "ppt/presentation.xml" not in archive.namelist():
                raise DocumentProcessingError("The PPTX presentation is invalid or too large to process.")

            uncompressed_bytes = 0
            for entry in entries:
                if entry.flag_bits & 0x1:
                    raise DocumentProcessingError("Encrypted PPTX files are not supported.")
                uncompressed_bytes += entry.file_size
                if entry.file_size > MAX_PPTX_ENTRY_BYTES:
                    raise DocumentProcessingError("The PPTX contains an oversized embedded item.")
                if entry.file_size > 1024 * 1024 and entry.compress_size == 0:
                    raise DocumentProcessingError("The PPTX archive is invalid or unsafe to process.")
                if (
                    entry.file_size > 1024 * 1024
                    and entry.file_size / max(entry.compress_size, 1) > MAX_PPTX_COMPRESSION_RATIO
                ):
                    raise DocumentProcessingError("The PPTX archive is compressed beyond the processing limit.")
                if uncompressed_bytes > MAX_PPTX_UNCOMPRESSED_BYTES:
                    raise DocumentProcessingError("The PPTX expands beyond the 64 MiB processing limit.")
    except DocumentProcessingError:
        raise
    except (OSError, zipfile.BadZipFile) as error:
        raise DocumentProcessingError("The PPTX presentation could not be read.") from error


def _shape_text(shape) -> list[str]:
    parts: list[str] = []
    if getattr(shape, "has_text_frame", False):
        text = shape.text.strip()
        if text:
            parts.append(text)
    if getattr(shape, "has_table", False):
        for row in shape.table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            if any(cells):
                parts.append(" | ".join(cells))
    if getattr(getattr(shape, "shape_type", None), "name", None) == "GROUP":
        for child in shape.shapes:
            parts.extend(_shape_text(child))
    return parts


def _extract_pptx(content: bytes) -> list[TextSection]:
    _check_pptx_archive(content)
    try:
        presentation = Presentation(io.BytesIO(content))
        if len(presentation.slides) > MAX_DOCUMENT_PAGES:
            raise DocumentProcessingError("Presentations may contain at most 500 slides.")

        sections = []
        for slide_number, slide in enumerate(presentation.slides, start=1):
            text = "\n".join(part for shape in slide.shapes for part in _shape_text(shape))
            if text.strip():
                sections.append(TextSection(text=text, slide_number=slide_number))
                _check_extracted_size(sections)
    except DocumentProcessingError:
        raise
    except Exception as error:
        raise DocumentProcessingError("The PPTX presentation could not be read. Check the file and try again.") from error

    if not sections:
        raise DocumentProcessingError("No readable slide text was found in this presentation.")
    return sections


def extract_document(file_format: str, content: bytes) -> list[TextSection]:
    """Return non-empty text sections without crossing page or slide boundaries."""
    if file_format == "pdf":
        return _extract_pdf(content)
    if file_format == "txt":
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise DocumentProcessingError("TXT files must use UTF-8 encoding.") from error
        if not text.strip():
            raise DocumentProcessingError("No readable text was found in this TXT file.")
        if len(text) > MAX_EXTRACTED_CHARACTERS:
            raise DocumentProcessingError(
                "The extracted text is too large to process. Split the file into smaller documents."
            )
        return [TextSection(text=text)]
    if file_format == "pptx":
        return _extract_pptx(content)
    raise DocumentProcessingError("This document format is not supported for text extraction.")
