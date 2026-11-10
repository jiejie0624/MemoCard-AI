# MemoCard AI Database and Deployment Design

**Status:** pgvector direction approved; migration 006 is local and awaits review/application
**Scope:** Initial MVP relational data model and deployment constraints. This document does not create database objects or select new runtime services.

## 1. Deployment targets

- **Frontend:** React hosted on Vercel.
- **Backend:** Python + FastAPI hosted on Vercel Functions. Vercel currently documents the Python runtime as Beta. Function duration and package limits depend on the Vercel plan and configuration.
- **Relational database:** Neon PostgreSQL. Application traffic should use Neon's pooled connection endpoint. Schema migration and administrative workflows may need a separate direct connection. Store connection strings as deployment secrets, never in Git.
- **Vector search:** Neon PostgreSQL with the `pgvector` extension stores chunk embeddings beside their relational source records. This avoids a separately hosted vector database and keeps vector search in the approved Neon deployment.
- **Uploaded file storage:** Private Vercel Blob is selected for user documents. FastAPI uploads files through the Vercel Python SDK; the MVP caps each upload at 4 MiB to stay below Vercel Function's 4.5 MB request-body limit. Function-local files are not used for durable storage.

Long-running document extraction and indexing must fit the configured Vercel Function duration or be split into retryable steps. This document does not add a queue or background-job service.

## 2. Proposed ERD

The ERD is a proposal, not a migration or approved final schema.

~~~mermaid
erDiagram
    USER ||--o{ DOCUMENT : owns
    DOCUMENT ||--o{ DOCUMENT_CHUNK : contains
    USER ||--o{ CHAT_SESSION : owns
    CHAT_SESSION ||--o{ CHAT_SESSION_DOCUMENT : searches
    DOCUMENT ||--o{ CHAT_SESSION_DOCUMENT : selected_for
    CHAT_SESSION ||--o{ CHAT_MESSAGE : contains
    CHAT_MESSAGE ||--o{ MESSAGE_CITATION : cites
    DOCUMENT_CHUNK ||--o{ MESSAGE_CITATION : referenced_by
    USER ||--o{ FLASHCARD : owns
    CHAT_MESSAGE o|--o{ FLASHCARD : may_generate
    FLASHCARD ||--o{ FLASHCARD_SOURCE : has
    DOCUMENT ||--o{ FLASHCARD_SOURCE : supports
    FLASHCARD ||--o{ FLASHCARD_REVIEW : reviewed_in
~~~

## 3. PostgreSQL tables

Use UUID primary keys for application entities, timestamptz for timestamps, and foreign keys for relationships. PostgreSQL is authoritative for ownership and structured records.

| Table | Important fields and purpose |
|---|---|
| users | id, email, password_hash, display_name, timezone, created_at. Email is unique after normalization. Passwords are stored only as one-way hashes. timezone is an IANA timezone name and defaults to UTC. |
| documents | id, user_id, original_filename, file_format, storage_key, size_bytes, status, error_message, created_at, updated_at, deleted_at. Status tracks upload and processing progress (`uploaded` → `processing` → `chunked` → `ready`, or `failed`). The binary file is kept in private Vercel Blob; PostgreSQL stores its private pathname and metadata. |
| document_chunks | id, document_id, chunk_index, content, page_number, slide_number, content_hash, embedding vector(384), created_at. PostgreSQL stores source text, location, and the multilingual E5 embedding together for retrieval and citations. |
| chat_sessions | id, user_id, title, created_at, updated_at. Owns one conversation and its optional persistent document scope. |
| chat_session_documents | user_id, session_id, document_id, created_at. If rows exist, the chat searches only those documents; if none exist, it searches all of the user's ready documents. Composite foreign keys enforce same-user ownership. |
| chat_messages | id, session_id, role, content, created_at. Roles are user or assistant; messages share the same ordered conversation. |
| message_citations | message_id, document_chunk_id, rank, excerpt, page_number, slide_number. Connects an assistant response to the retrieved sources and source locations used to generate it. |
| flashcards | id, user_id, source_message_id (nullable), question, answer, repetition_count, ease_factor, interval_days, last_reviewed_at, next_review_at, created_at, updated_at. The scheduling fields hold the current SM-2 state. |
| flashcard_sources | flashcard_id, document_id, optional document_chunk_id. Allows a card to have multiple source documents and chunks. |
| flashcard_reviews | id, flashcard_id, quality (SM-2 score 0-5), reviewed_at, idempotency_key, and before/after scheduling values. This is the history of review events. |

### Revision calendar

Do not create a separate revision_schedules table for the MVP. The current schedule is represented by flashcards.next_review_at; the calendar queries due and upcoming cards for the current user. flashcard_reviews records review history. A separate schedule table can be reconsidered if users later need multiple plans or manual rescheduling.

## 4. Ownership and integrity

- Every user-owned API operation must verify ownership in PostgreSQL before returning or changing data.
- Vector retrieval must join chunks to their document and filter by the authenticated user's ID and `documents.status = 'ready'`; a vector match alone never grants access.
- Keeping vectors in Neon lets ownership filters and vector similarity run in one PostgreSQL query and transaction. It avoids cross-database indexing and deletion consistency problems.
- Indexes should support common access paths: unique normalized email; documents by (user_id, status); chunks by (document_id, chunk_index); messages by (session_id, created_at); and due flashcards by (user_id, next_review_at).
- Document deletion and retention need an explicit policy because documents can be referenced by chat citations and flashcard sources. The initial implementation should not hard-delete a document until its relational references are handled consistently.
- A migration should enforce ownership consistency across relationships, preferably with composite foreign keys where practical. The exact constraints and delete behavior must be fixed before implementation.

## 5. Data flow across services

1. Store an upload in the selected durable file store and create its documents record in PostgreSQL.
2. Extract and split the file; record stable chunk identifiers and source locations in PostgreSQL. `chunked` means text extraction is complete but vector embedding is pending.
3. Generate multilingual E5 embeddings locally with FastEmbed and save all vectors to `document_chunks` in one transaction.
4. Mark the document ready only after all vectors have been stored; preserve a retryable error status on failure.
5. For chat, verify session ownership and document scope, retrieve matching pgvector chunks with owner/status filters, call DeepSeek with recent history and labelled excerpts, then save both messages and verified citation links in one PostgreSQL transaction.
6. Save flashcards and source links in PostgreSQL; update SM-2 state and append a review event on each review.

Chunk content and embeddings share the same PostgreSQL transaction, so a document cannot become `ready` with a partial vector index. AI failures do not save a half-complete chat turn.

## 6. Decisions to settle before their implementation phase

1. What document deletion policy should preserve or remove existing citations and flashcard sources?
2. Should the proposal's one-click flashcard generation, TTS, tagging, and 15-student SUS/accuracy evaluation be tracked as post-MVP requirements? The current AGENTS.md places TTS and tagging after the MVP but does not define the research evaluation work.

Migration 003 adds users.timezone and a per-user flashcard review idempotency key; migration 004 adds PPTX and a retryable document-deletion state; migration 005 adds the `chunked` processing state; migration 006 adds pgvector embeddings; migration 007 adds persistent chat document scope. These files exist locally and have not been applied to Neon. The Vercel Blob store still needs to be created and connected in the Vercel project before live uploads can run.

## 7. Official deployment references

- [Vercel Python runtime](https://vercel.com/docs/functions/runtimes/python)
- [Vercel Function limitations](https://vercel.com/docs/functions/limitations)
- [Neon serverless connection pooling guide](https://github.com/neondatabase/website/blob/main/content/docs/guides/serverless-connection-pooling.md)
- [Neon pgvector guide](https://neon.com/docs/extensions/pgvector)
