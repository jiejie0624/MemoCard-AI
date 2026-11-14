# MemoCard AI — Detailed Handoff for the Next AI

Updated: 2026-11-10, Asia/Kuala_Lumpur

This note is a handoff, not an instruction to skip the project's approval workflow. The immediate goal is to continue debugging document processing without losing the diagnosis or repeating earlier steps.

## 1. Start here

1. Read the actual root `AGENTS.md` from disk before changing source. The user supplied a replacement version in chat; it changes vector storage to **Neon PostgreSQL + `pgvector`** (there is no ChromaDB in the current architecture). Verify the on-disk file is the same version.
2. Check `git status --short --branch` and recent history. Preserve all history; never reset or force-push.
3. The current user issue is an uploaded PPTX that still cannot be processed. The timeout fix below has already been proposed and approved, but was **not implemented yet** when this note was written.
4. Implement only that approved change. Do not broaden it into a background-worker redesign, dependency change, database change, or embedding-provider replacement without discussing it first.

## 2. Product and architecture

MemoCard AI is a responsive React + FastAPI learning app. Main workflow:

1. Upload PDF, UTF-8 TXT, or PPTX.
2. Store document bytes in a **private Vercel Blob** store and metadata/chunks/embeddings in Neon PostgreSQL with `pgvector`.
3. Extract and chunk text while preserving page/slide sources; create local embeddings with FastEmbed.
4. Retrieve relevant chunks from PostgreSQL and call DeepSeek for RAG answers with citations.
5. Generate/edit/save flashcards and schedule review using SM-2.

Hosting: React frontend and FastAPI backend are separate Render services. Database is Neon. Uploaded files use Vercel Blob. DeepSeek is the LLM provider. Do not switch these services or add runtime dependencies without following `AGENTS.md` approval rules.

## 3. Git and current workspace state

- Repo: `C:\Users\ngjun\Downloads\Memocard AI`
- Branch: `feature/authentication`
- Remote: `origin` → `https://github.com/jiejie0624/MemoCard-AI.git`
- Last source commit, pushed to origin: `b706dac` — `fix: use psycopg cursors for batch writes`
- GitHub and Render were both confirmed at `b706dac`; Render API deployment was live (`dep-dbpbe10ae00c73e5058g`).
- At handoff creation the only worktree change was this new, untracked `AI_HANDOFF.md`; there were no pending source edits.
- Do not claim this handoff file or the next code change is committed. Do not push without giving the user the file list, commit, and branch and then receiving explicit approval.

## 4. Implemented before the current issue

### Language switcher

- English is the first-use default, with English/Chinese toggle persisted in local storage.
- Commit before current HEAD history: `6e6874d feat: add English and Chinese language switcher`.

### Document batch-write fix

- The API had been calling nonexistent `psycopg.Connection.executemany()` in document chunk inserts/vector updates and chat document-scope inserts.
- Fixed to use `connection.cursor().executemany()` in `backend/app/documents/repository.py` and `backend/app/chat/repository.py`.
- Commit: `b706dac fix: use psycopg cursors for batch writes`.
- Pushed and deployed to Render.

### Blob/API configuration

- User created a **Private** Vercel Blob store and configured `BLOB_READ_WRITE_TOKEN` in the Render API service.
- Render environment showed both `BLOB_READ_WRITE_TOKEN` and `DEEPSEEK_API_KEY` variable names present; never reveal their values. Presence alone does not prove DeepSeek works.
- A document upload reached `201 Created`, so Blob upload and document metadata creation succeeded at least once.

## 5. Exact current error and evidence

The user first saw `The extracted text could not be saved. Retry processing.` This came from the `AttributeError` on `connection.executemany()`. That fix was pushed and deployed.

After the user retried the PPTX against the new deployment, the failure changed. Latest user screenshot showed two messages: `Can't connect to the materials service. Check your connection and try again.` The Render logs around that attempt showed:

- The deployment of `b706dac` was live before this retry.
- `POST /api/documents` returned `201 Created` at about 14:21 MYT.
- The first FastEmbed model initialization downloaded five files; download/model setup took about 24 seconds. Logs included an unauthenticated Hugging Face Hub warning. This is not itself proof of failure.
- The frontend's `requestDocuments()` uses `AbortSignal.timeout(20000)` by default. A slow first model startup can exceed that 20-second browser timeout.
- Render logged the API instance restarting at about 14:22 MYT and then starting Uvicorn again.
- The screenshot's generic connection error plausibly follows the client timeout and/or instance restart.

**Do not state a definitive restart cause.** The logs seen so far did not establish OOM, nor prove that the model download alone caused the Render restart. First model initialization is slow; instance restart is also confirmed. Keep those facts distinct.

The existing PPTX should still be in the account because the upload returned 201. Before asking for another upload, inspect the current document status in the app and use its retry action if available. Do not assume it was deleted.

## 6. Approved next change — implement this only

The user explicitly approved increasing the **document-processing request** timeout from 20 seconds to 120 seconds, while leaving normal material list/upload/delete requests at 20 seconds.

Only edit `src/documents/DocumentsPage.jsx`.

Current relevant shape:

```js
async function requestDocuments(path, options = {}) {
  // fetch(... signal: options.signal || AbortSignal.timeout(20000))
}
```

`handleUpload()` first posts the file to `POST /api/documents`, then calls `POST /api/documents/{id}/process`. `retryProcessing()` calls that same `/process` endpoint. The initial upload must retain the normal timeout; only the potentially slow processing calls should get 120 seconds. `loadDocuments()` and polling should remain at 20 seconds.

One straightforward implementation is to add a third helper parameter, e.g. `timeoutMs = 20000`, and use it only to build the default `AbortSignal.timeout(timeoutMs)`. Then pass `120000` as the third argument for the two `POST .../process` calls. Do not spread this helper-only timeout value into `fetch` options. Preserve explicitly supplied `options.signal` behavior.

No database/schema changes, dependency changes, backend redesign, or storage changes are approved in this task.

## 7. Verification and release sequence

After implementation:

1. Inspect the diff and run `git diff --check`.
2. Use the project's appropriate verification commands; report exactly what was and was not run. Avoid claiming this fixes a Render instance restart unless confirmed by a new processing attempt and logs.
3. Report the modified file(s), current branch, and local commit status. Let the user review before committing.
4. After review/approval, create a truthful Conventional Commit (possible message: `fix: allow time for document embedding startup`).
5. Before pushing, list changed files, commit contents/hash, and target branch; wait for explicit push approval.
6. After the Render deployment for the new commit is marked **Live**, retry processing the existing PPTX. Do not retry while a deployment is still in progress.
7. Inspect new Render logs and document status. If it still fails, identify whether it is timeout, model initialization, a database error, or an instance restart before proposing the next change.

## 8. Secret safety

During a previous Render dashboard inspection, an accessibility result unexpectedly exposed the Blob token as plain text. The user was advised to rotate it; whether rotation was completed is unknown. Never copy secret values into this file, chat, logs, or tool output. If needed, inspect only whether a variable is present, not its value, and ask the user to confirm rotation. Never read/show the DeepSeek key either.

## 9. Files to inspect for this task

- `src/documents/DocumentsPage.jsx` — frontend fetch timeout, upload, process, retry, and list polling.
- `backend/app/documents/routes.py` — extraction/chunking/embedding route and safe generic errors.
- `backend/app/documents/repository.py` — Neon chunk/vector persistence (Psycopg cursor fix already deployed).
- `backend/app/processing/embeddings.py` — local multilingual E5/FastEmbed model initialization.
- `backend/app/chat/repository.py` — Psycopg cursor fix already deployed.
- `render.yaml` — Render service configuration (read only unless a separately approved change is needed).
