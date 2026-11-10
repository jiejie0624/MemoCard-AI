import { useEffect, useRef, useState } from "react";
import { apiUrl } from "../api.js";

const MAX_FILE_BYTES = 4 * 1024 * 1024;
const ACCEPTED_FORMATS = ".pdf,.txt,.pptx";

function formatSize(size) {
  if (size < 1024 * 1024) return `${Math.max(1, Math.round(size / 1024))} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(value) {
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(new Date(value));
}

function statusLabel(status) {
  const labels = {
    uploading: "正在上传",
    uploaded: "等待处理",
    processing: "处理中",
    chunked: "文字已提取，等待索引",
    ready: "可用于问答",
    failed: "处理失败",
    deleting: "等待完成删除",
  };
  return labels[status] || "状态未知";
}

function responseError(status, detail) {
  if (status === 401) return "登录状态已失效，请重新登录。";
  if (status === 413) return "文件超过 4 MiB 上限，请选择较小的文件。";
  if (status === 415) return "目前支持 PDF、UTF-8 TXT 和 PPTX。";
  if (status === 422) {
    if (detail?.includes("PDF")) return "文件内容与 PDF 格式不匹配，请检查文件后重试。";
    if (detail?.includes("PPTX")) return "文件不是有效的 PPTX 演示文稿。";
    if (detail?.includes("UTF-8")) return "TXT 文件需要使用 UTF-8 编码。";
    return "请检查文件是否为空或名称是否有效。";
  }
  if (status === 503) return "私有文件存储暂时不可用，请稍后重试。";
  return typeof detail === "string" ? detail : "暂时无法完成操作，请稍后重试。";
}

async function requestDocuments(path, options = {}) {
  let response;
  try {
    response = await fetch(apiUrl(`/api/documents${path}`), {
      ...options,
      credentials: "include",
      signal: options.signal || AbortSignal.timeout(20000),
    });
  } catch {
    throw new Error("无法连接资料服务，请检查网络后重试。");
  }

  if (response.status === 204) return null;
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    // The browser can still show a safe fallback for non-JSON server errors.
  }
  if (!response.ok) {
    throw new Error(responseError(response.status, payload?.detail));
  }
  return payload;
}

function DocumentRow({ document, onDelete, onRetryDelete, onRetryProcessing, deleting, processing }) {
  const extension = document.file_format.toUpperCase();
  const isPendingDelete = document.status === "deleting";
  const canRetryProcessing = document.status === "uploaded" || document.status === "failed";

  return (
    <li className="document-row">
      <span className={`document-file-mark document-file-${document.file_format}`} aria-hidden="true">
        {extension}
      </span>
      <div className="document-row-main">
        <strong className="document-filename" title={document.original_filename}>
          {document.original_filename}
        </strong>
        <span className="document-metadata">
          {formatSize(document.size_bytes)} <span aria-hidden="true">·</span> {formatDate(document.created_at)}
        </span>
        {document.error_message && (
          <span className="document-inline-error" role="status">
            {isPendingDelete ? "文件已从资料列表中停用，存储清理尚未完成。" : document.error_message}
          </span>
        )}
      </div>
      <span className={`document-status document-status-${document.status}`}>
        <span className="document-status-dot" aria-hidden="true" />
        {statusLabel(document.status)}
      </span>
      <div className="document-row-actions">
        {!isPendingDelete && (
          <a
            className="document-action"
            href={apiUrl(`/api/documents/${document.id}/file`)}
            aria-label={`下载${document.original_filename}`}
          >
            下载
          </a>
        )}
        {isPendingDelete ? (
          <button
            className="document-action document-action-retry"
            type="button"
            onClick={() => onRetryDelete(document)}
            disabled={deleting}
          >
            {deleting ? "清理中…" : "重试清理"}
          </button>
        ) : canRetryProcessing ? (
          <button
            className="document-action document-action-retry"
            type="button"
            onClick={() => onRetryProcessing(document)}
            disabled={processing}
          >
            {processing ? "处理中…" : document.status === "failed" ? "重试处理" : "开始处理"}
          </button>
        ) : (
          <button
            className="document-action document-action-delete"
            type="button"
            onClick={() => onDelete(document)}
            disabled={deleting}
          >
            删除
          </button>
        )}
      </div>
    </li>
  );
}

export default function DocumentsPage() {
  const fileInput = useRef(null);
  const deleteDialog = useRef(null);
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [deletingId, setDeletingId] = useState(null);
  const [processingId, setProcessingId] = useState(null);
  const [pageError, setPageError] = useState("");
  const [operationError, setOperationError] = useState("");
  const [confirmingDocument, setConfirmingDocument] = useState(null);
  const hasProcessing = documents.some((document) => document.status === "processing");

  useEffect(() => {
    const dialog = deleteDialog.current;
    if (!dialog) return;
    if (confirmingDocument && !dialog.open) dialog.showModal();
    if (!confirmingDocument && dialog.open) dialog.close();
  }, [confirmingDocument]);

  async function loadDocuments(signal) {
    setLoading(true);
    setPageError("");
    try {
      const items = await requestDocuments("", { signal });
      setDocuments(items);
    } catch (error) {
      if (!signal?.aborted) setPageError(error.message);
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }

  useEffect(() => {
    const controller = new AbortController();
    loadDocuments(controller.signal);
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!hasProcessing) return undefined;
    const controller = new AbortController();
    const refresh = async () => {
      try {
        const items = await requestDocuments("", { signal: controller.signal });
        setDocuments(items);
      } catch {
        // Keep the last known state visible when a background refresh briefly fails.
      }
    };
    const timer = window.setInterval(refresh, 2000);
    return () => {
      window.clearInterval(timer);
      controller.abort();
    };
  }, [hasProcessing]);

  async function handleUpload(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (file.size > MAX_FILE_BYTES) {
      setOperationError("文件超过 4 MiB 上限，请选择较小的文件。");
      return;
    }

    setUploading(true);
    setOperationError("");
    const form = new FormData();
    form.append("file", file);
    try {
      const uploaded = await requestDocuments("", { method: "POST", body: form });
      setProcessingId(uploaded.id);
      await requestDocuments(`/${uploaded.id}/process`, { method: "POST" });
      await loadDocuments();
    } catch (error) {
      setOperationError(error.message);
      await loadDocuments();
    } finally {
      setUploading(false);
      setProcessingId(null);
    }
  }

  async function retryProcessing(document) {
    setProcessingId(document.id);
    setOperationError("");
    try {
      await requestDocuments(`/${document.id}/process`, { method: "POST" });
      await loadDocuments();
    } catch (error) {
      setOperationError(error.message);
      await loadDocuments();
    } finally {
      setProcessingId(null);
    }
  }

  async function performDelete(document) {
    setDeletingId(document.id);
    setOperationError("");
    try {
      await requestDocuments(`/${document.id}`, { method: "DELETE" });
      setConfirmingDocument(null);
      await loadDocuments();
    } catch (error) {
      setOperationError(error.message);
      setConfirmingDocument(null);
      await loadDocuments();
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div className="workspace-content documents-content">
      <header className="dashboard-heading">
        <div>
          <p className="eyebrow">MEMOCARD AI · 学习资料</p>
          <h1>整理你的课程资料</h1>
          <p className="dashboard-subtitle">先把资料收好；处理完成后，就能用它们进行带来源的问答。</p>
        </div>
        <span className="workspace-status">
          <span className="status-dot" aria-hidden="true" />
          私人资料空间
        </span>
      </header>

      <section className="documents-panel" aria-labelledby="documents-heading">
        <div className="documents-panel-heading">
          <div>
            <h2 id="documents-heading">你的资料</h2>
            <p>文件只对你的账号开放。</p>
          </div>
          <button
            className="primary-button documents-upload-button"
            type="button"
            onClick={() => fileInput.current?.click()}
            disabled={uploading}
          >
            <span aria-hidden="true">＋</span>
            {uploading ? "正在上传…" : "上传资料"}
          </button>
          <input
            ref={fileInput}
            className="visually-hidden"
            type="file"
            accept={ACCEPTED_FORMATS}
            onChange={handleUpload}
            disabled={uploading}
            aria-label="选择要上传的学习资料"
          />
        </div>

        <div className="documents-upload-hint">
          <span className="upload-hint-mark" aria-hidden="true">↑</span>
          <div>
            <strong>支持 PDF、UTF-8 TXT 和 PPTX</strong>
            <p>单个文件最大 4 MiB。旧式 PPT 暂不支持。</p>
          </div>
          {(uploading || processingId) && (
            <span className="uploading-indicator" role="status">
              {uploading ? "正在安全上传" : "正在提取文字并整理来源"}
            </span>
          )}
        </div>

        {operationError && <p className="documents-error" role="alert">{operationError}</p>}
        {pageError && (
          <div className="documents-load-error" role="alert">
            <p>{pageError}</p>
            <button className="text-button" type="button" onClick={() => loadDocuments()}>
              重新加载
            </button>
          </div>
        )}

        {loading ? (
          <div className="documents-loading" role="status">
            <span className="loading-mark" aria-hidden="true">M</span>
            <span>正在读取资料…</span>
          </div>
        ) : !pageError && documents.length === 0 ? (
          <div className="documents-empty">
            <span className="empty-folder-mark" aria-hidden="true">＋</span>
            <h3>这里还没有资料</h3>
            <p>上传一份课程资料，之后就能在学习空间中继续整理和复习。</p>
          </div>
        ) : (
          <ul className="document-list" aria-label="学习资料列表">
            {documents.map((document) => (
              <DocumentRow
                key={document.id}
                document={document}
                onDelete={setConfirmingDocument}
                onRetryDelete={performDelete}
                onRetryProcessing={retryProcessing}
                deleting={deletingId === document.id}
                processing={processingId === document.id}
              />
            ))}
          </ul>
        )}
      </section>

      <dialog
        ref={deleteDialog}
        className="profile-dialog document-delete-dialog"
        aria-labelledby="document-delete-title"
        onCancel={(event) => {
          event.preventDefault();
          setConfirmingDocument(null);
        }}
        onClose={() => setConfirmingDocument(null)}
      >
        <div className="profile-dialog-heading">
          <div>
            <p className="eyebrow">删除资料</p>
            <h2 id="document-delete-title">确定删除这份资料？</h2>
          </div>
          <button
            className="dialog-close"
            type="button"
            aria-label="取消删除"
            onClick={() => setConfirmingDocument(null)}
          >
            ×
          </button>
        </div>
        <p className="document-delete-copy">
          {confirmingDocument?.original_filename} 将从你的资料列表中移除，文件也会从私有存储清理。
        </p>
        <div className="profile-actions">
          <button
            className="cancel-button"
            type="button"
            onClick={() => setConfirmingDocument(null)}
            disabled={deletingId !== null}
          >
            保留资料
          </button>
          <button
            className="danger-button"
            type="button"
            onClick={() => confirmingDocument && performDelete(confirmingDocument)}
            disabled={deletingId !== null}
          >
            {deletingId ? "正在清理…" : "确认删除"}
          </button>
        </div>
      </dialog>
    </div>
  );
}
