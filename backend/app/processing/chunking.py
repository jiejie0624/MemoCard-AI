"""Deterministic, source-preserving chunks for later embedding and citations."""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from dataclasses import dataclass
from uuid import UUID, uuid5

from backend.app.processing.extraction import DocumentProcessingError, TextSection


TARGET_UNITS = 600
OVERLAP_UNITS = 80
MAX_CHUNKS = 10_000
_CJK_RUN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af\U00020000-\U0002EBEF]+")
_LEXEME = re.compile(
    r"[\u3400-\u4dbf\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af\U00020000-\U0002EBEF]+"
    r"|[^\W_]+(?:['’][^\W_]+)*|[^\s]",
    re.UNICODE,
)
_SENTENCE_ENDINGS = {".", "!", "?", "。", "！", "？", ";", "；"}


@dataclass(frozen=True)
class DocumentChunk:
    id: UUID
    chunk_index: int
    content: str
    page_number: int | None
    slide_number: int | None
    content_hash: str


@dataclass(frozen=True)
class _Token:
    start: int
    end: int
    text: str
    weight: int


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))
    text = text.replace("\x00", "")
    text = re.sub(r"[\t\f\v ]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _tokens(text: str) -> list[_Token]:
    tokens: list[_Token] = []
    for match in _LEXEME.finditer(text):
        value = match.group()
        if _CJK_RUN.fullmatch(value):
            tokens.extend(
                _Token(match.start() + offset, match.start() + offset + 1, char, 1)
                for offset, char in enumerate(value)
            )
            continue

        if value.isalnum() or "_" in value or "'" in value or "’" in value:
            weight = max(1, math.ceil(len(value) / 4))
        else:
            weight = 1

        # Pathological unbroken strings must not make a single oversized chunk.
        max_piece_length = TARGET_UNITS * 4
        if weight > TARGET_UNITS and len(value) > max_piece_length:
            for offset in range(0, len(value), max_piece_length):
                piece = value[offset : offset + max_piece_length]
                start = match.start() + offset
                tokens.append(_Token(start, start + len(piece), piece, math.ceil(len(piece) / 4)))
        else:
            tokens.append(_Token(match.start(), match.end(), value, weight))
    return tokens


def _chunk_section(section: TextSection) -> list[str]:
    text = _normalize(section.text)
    tokens = _tokens(text)
    if not tokens:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(tokens):
        end = start
        total = 0
        while end < len(tokens) and (total + tokens[end].weight <= TARGET_UNITS or end == start):
            total += tokens[end].weight
            end += 1

        if end < len(tokens):
            # Prefer a nearby sentence boundary when it keeps the chunk near its target size.
            sentence_ends = [
                index + 1
                for index in range(start, end)
                if tokens[index].text in _SENTENCE_ENDINGS
            ]
            for candidate in reversed(sentence_ends):
                candidate_units = sum(token.weight for token in tokens[start:candidate])
                if candidate_units >= int(TARGET_UNITS * 0.75):
                    end = candidate
                    break

        content = text[tokens[start].start : tokens[end - 1].end].strip()
        if content:
            chunks.append(content)
        if end >= len(tokens):
            break

        next_start = end
        overlap = 0
        while next_start > start and overlap < OVERLAP_UNITS:
            next_start -= 1
            overlap += tokens[next_start].weight
        start = max(start + 1, next_start)

    return chunks


def build_document_chunks(document_id: UUID, sections: list[TextSection]) -> list[DocumentChunk]:
    """Build deterministic chunk IDs and hashes while retaining each source locator."""
    chunks: list[DocumentChunk] = []
    for section in sections:
        for content in _chunk_section(section):
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            chunk_index = len(chunks)
            chunk_id = uuid5(document_id, f"chunk:{chunk_index}:{content_hash}")
            chunks.append(
                DocumentChunk(
                    id=chunk_id,
                    chunk_index=chunk_index,
                    content=content,
                    page_number=section.page_number,
                    slide_number=section.slide_number,
                    content_hash=content_hash,
                )
            )
            if len(chunks) > MAX_CHUNKS:
                raise DocumentProcessingError("The document produces too many text chunks to process safely.")
    return chunks
