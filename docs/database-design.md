# MemoCard AI Database and Deployment Design

**Status:** Proposed for developer review  
**Scope:** Initial MVP relational data model and deployment constraints. This document does not create database objects or select new runtime services.

## 1. Deployment targets

- **Frontend:** React hosted on Vercel.
- **Backend:** Python + FastAPI hosted on Vercel Functions. Vercel currently documents the Python runtime as Beta. Function duration and package limits depend on the Vercel plan and configuration.
- **Relational database:** Neon PostgreSQL. Application traffic should use Neon's pooled connection endpoint. Schema migration and administrative workflows may need a separate direct connection. Store connection strings as deployment secrets, never in Git.
- **Vector database:** ChromaDB remains the selected vector database. Chroma's local persistent client is intended for development and testing; production should connect to a server-backed Chroma deployment. A hosted Chroma service or separately hosted Chroma server has not been selected.
- **Uploaded file storage:** Vercel Function request bodies are limited to 4.5 MB, and function-local files are not durable storage. The MVP therefore needs a durable upload-storage decision before implementing document upload. Vercel Blob is one possible option, but it is an additional service and is not approved or selected here.

Long-running document extraction and indexing must fit the configured Vercel Function duration or be split into retryable steps. This document does not add a queue or background-job service.

## 2. Proposed ERD

The ERD is a proposal, not a migration or approved final schema.

~~~mermaid
erDiagram
    USER ||--o{ DOCUMENT : owns
    DOCUMENT ||--o{ DOCUMENT_CHUNK : contains
    USER ||--o{ CHAT_SESSION : owns
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
| users | id, email, password_hash, display_name, created_at. Email is unique after normalization. Passwords are stored only as one-way hashes. |
| documents | id, user_id, original_filename, media_type, storage_key, size_bytes, status, error_message, created_at, updated_at. Status tracks upload and processing progress. The binary file is kept outside PostgreSQL; the storage provider remains undecided. |
| document_chunks | id, document_id, chunk_index, content, page_number, slide_number, content_hash, created_at. The stable UUID maps to a Chroma record. PostgreSQL keeps the chunk text and source metadata for citations and reindexing; Chroma stores the embedding and a copy of the chunk text for retrieval. |
| chat_sessions | id, user_id, title, created_at, updated_at. By default, a session searches the current user's ready documents unless a later decision adds per-session document selection. |
| chat_messages | id, session_id, role, content, created_at. Roles are user or assistant; messages share the same ordered conversation. |
| message_citations | message_id, document_chunk_id, rank, excerpt, page_number, slide_number. Connects an assistant response to the retrieved sources and source locations used to generate it. |
| flashcards | id, user_id, source_message_id (nullable), question, answer, repetition_count, ease_factor, interval_days, last_reviewed_at, next_review_at, created_at, updated_at. The scheduling fields hold the current SM-2 state. |
| flashcard_sources | flashcard_id, document_id, optional document_chunk_id. Allows a card to have multiple source documents and chunks. |
| flashcard_reviews | id, flashcard_id, quality (SM-2 score 0-5), reviewed_at, and before/after scheduling values. This is the history of review events. |

### Revision calendar

Do not create a separate revision_schedules table for the MVP. The current schedule is represented by flashcards.next_review_at; the calendar queries due and upcoming cards for the current user. flashcard_reviews records review history. A separate schedule table can be reconsidered if users later need multiple plans or manual rescheduling.

## 4. Ownership and integrity

- Every user-owned API operation must verify ownership in PostgreSQL before returning or changing data.
- Chroma metadata should include stable identifiers such as user_id, document_id, and document_chunk_id; retrieval must be filtered to the authenticated user's documents.
- Chroma does not share PostgreSQL foreign keys or transactions. PostgreSQL IDs are cross-store references, and indexing/deletion operations need retryable status transitions.
- Indexes should support common access paths: unique normalized email; documents by (user_id, status); chunks by (document_id, chunk_index); messages by (session_id, created_at); and due flashcards by (user_id, next_review_at).
- Document deletion and retention need an explicit policy because documents can be referenced by chat citations and flashcard sources. The initial implementation should not hard-delete a document until its Chroma records and relational references are handled consistently.
- A migration should enforce ownership consistency across relationships, preferably with composite foreign keys where practical. The exact constraints and delete behavior must be fixed before implementation.

## 5. Data flow across services

1. Store an upload in the selected durable file store and create its documents record in PostgreSQL.
2. Extract and split the file; record stable chunk identifiers and source locations in PostgreSQL.
3. Write chunk text, embeddings, and identifying metadata to Chroma using those stable identifiers.
4. Mark the document ready only after indexing succeeds; preserve a retryable error status on failure.
5. For chat, verify the user's documents, retrieve matching Chroma chunks with a user filter, save messages and citation links in PostgreSQL, and call DeepSeek with the retrieved context.
6. Save flashcards and source links in PostgreSQL; update SM-2 state and append a review event on each review.

The sequence must account for partial failure because PostgreSQL and Chroma cannot participate in one transaction.

## 6. Decisions to settle before implementation

1. Which durable file-storage service will hold uploaded PDFs, TXT, and PPT files?
2. Will production Chroma be hosted by a managed Chroma service or by a separately operated Chroma server?
3. Should chat search all of a user's ready documents, or should each session select a subset?
4. What document deletion policy should preserve or remove existing citations and flashcard sources?
5. Should the proposal's one-click flashcard generation, TTS, tagging, and 15-student SUS/accuracy evaluation be tracked as post-MVP requirements? The current AGENTS.md places TTS and tagging after the MVP but does not define the research evaluation work.

No schema, migration, external service, application code, or package dependency is created by this proposal.

## 7. Official deployment references

- [Vercel Python runtime](https://vercel.com/docs/functions/runtimes/python)
- [Vercel Function limitations](https://vercel.com/docs/functions/limitations)
- [Neon serverless connection pooling guide](https://github.com/neondatabase/website/blob/main/content/docs/guides/serverless-connection-pooling.md)
- [Chroma deployment architecture](https://docs.trychroma.com/docs/overview/architecture)
- [Chroma Python clients](https://docs.trychroma.com/reference/python)
