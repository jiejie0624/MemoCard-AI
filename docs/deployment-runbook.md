# MemoCard AI Deployment Runbook

This runbook describes deployment preparation. It does not apply database migrations,
create a Vercel project or Blob store, configure secrets, or publish a deployment.

## Current repository setup

- Vite builds the React frontend with `npm run build` into `dist/`.
- Vercel builds and serves the React frontend as static assets.
- Render runs the FastAPI application from `backend.app.main:app`; `render.yaml` contains
  the free-service blueprint and server-only environment variable declarations.
- The frontend uses `VITE_API_BASE_URL` to send `/api/*` calls to the Render service.
- Render allows credentialed browser requests only from the exact `FRONTEND_ORIGINS`.
  Cross-site auth cookies use `COOKIE_SAMESITE=none` and remain Secure.
- `.python-version` pins the deployment interpreter to Python 3.12.
- `vercel.json` excludes tests, documentation, migrations, local environments, and
  generated Python bytecode from the Python Function bundle. No function duration is
  pinned; it must be checked against the selected Vercel plan and Fluid Compute setting.

## Vercel project settings

1. Set the project root to the repository root.
2. Confirm the detected Vite build command is `npm run build` and output directory is `dist`.
3. Set `VITE_API_BASE_URL` to the deployed Render service origin, without a trailing slash,
   for both Preview and Production builds as needed.
4. Keep backend secrets on Render only; do not expose them through `VITE_` variables.

## Render API settings

1. Create a Web Service from this repository using the checked-in `render.yaml` blueprint.
2. Set `DATABASE_URL` to Neon's pooled connection URL, `DEEPSEEK_API_KEY` to the server
   secret, and `BLOB_READ_WRITE_TOKEN` to the private Blob read/write token.
3. Set `FRONTEND_ORIGINS` to the exact Vercel Preview and Production origins that should
   be allowed, comma-separated. Do not use `*` with credentialed cookies.
4. Render Free services sleep after 15 minutes of inactivity and have limited memory. The
   local embedding model may exceed that memory; verify a small synthetic TXT upload before
   relying on document processing. The free filesystem is ephemeral, so all uploaded files
   must continue to use Blob storage.
5. Cross-site cookies require `COOKIE_SAMESITE=none`, HTTPS, and credentialed CORS. Some
   browsers may block third-party cookies; if so, use a same-site custom domain or a
   same-origin proxy design before production use.

## Neon database setup

1. Select a dedicated development branch or verify the target database is empty. Do not
   assume migrations are absent just because the application is not connected yet.
2. Inspect the target schema before applying anything. These migrations have no migration
   ledger; several statements are not safe to repeat.
3. Apply each file once, in numeric order, using Neon's SQL Editor or a direct (not pooled)
   administrative connection:
   `001_initial_schema.sql` → `002_auth_sessions.sql` →
   `003_flashcard_review_timezone.sql` → `004_document_upload_lifecycle.sql` →
   `005_document_chunking_state.sql` → `006_document_chunk_embeddings.sql` →
   `007_chat_session_document_scope.sql`.
4. Confirm `users.timezone`, `flashcard_reviews.idempotency_key`, document lifecycle
   states, `document_chunks.embedding vector(384)`, the HNSW index, and
   `chat_session_documents` exist before connecting the app.
5. Put only the pooled connection URL in Vercel's `DATABASE_URL`; reserve a direct URL
   for schema migration and administrative work. Never put either URL in Git or chat.

## Preview smoke test

Use only a dedicated test account and a small synthetic TXT document:

1. `GET /api/auth/me` returns `401` before sign-in.
2. Register, refresh the page, then sign out and sign in again; the session cookie is
   HttpOnly, SameSite=Lax, and Secure in hosted environments.
3. Upload the synthetic TXT, process it, and confirm the document becomes `ready` only
   after its PostgreSQL chunks and vectors are stored.
4. Ask a question grounded in that text; check its citation and that an unrelated user
   cannot retrieve the document or conversation.
5. Generate a flashcard draft, edit it, confirm it, then review it and check the next due
   date, dashboard counts, and calendar entry.
6. Check Function logs and bundle/build output for timeout, memory, model-download, or
   package-size failures. Python Functions have a documented 500 MB uncompressed bundle
   limit, and the embedding model is downloaded when first needed.

Do not run this smoke test against a production account or upload real course materials
until the Preview flow has passed.

## Local parity checks

The project's local Vite proxy targets a separate FastAPI process on port 8000. For
Vercel route-emulation checks, use the Vercel CLI after connecting it to a safe Preview
project. Do not link the CLI to an unknown account or production project automatically.

## Official references

- [Vercel Python runtime](https://vercel.com/docs/functions/runtimes/python)
- [Deploy a FastAPI app on Vercel](https://vercel.com/docs/frameworks/backend/fastapi)
- [Vercel Function duration](https://vercel.com/docs/functions/configuring-functions/duration)
- [Vercel private Blob storage](https://vercel.com/docs/vercel-blob/private-storage)
- [Neon connection pooling](https://neon.com/docs/connect/connection-pooling)
- [Neon pgvector](https://neon.com/docs/extensions/pgvector)
- [DeepSeek Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/)
