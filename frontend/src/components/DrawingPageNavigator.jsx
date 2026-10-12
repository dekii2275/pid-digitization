import { useEffect, useMemo, useState } from 'react';
import { pageThumbnailUrl, savePageStatus } from '../services/documents';
import { getDocument } from '../services/annotations';

const PAGE_STATUS_LABELS = {
  not_started: 'Chưa làm',
  in_progress: 'Đang làm',
  pending_review: 'Chờ kiểm tra',
  completed: 'Hoàn tất',
};
const workflowOf = (document, page) =>
  document.page_workflows?.[page] || { status: 'not_started', revision: 0, annotation_revision: 0 };
const PAGE_SIZE = 12;

export function PageStatusSelect({ document, page, onUpdated, disabled }) {
  return (
    <PageStatusControl
      key={`${document.id}-${page}`}
      document={document}
      page={page}
      onUpdated={onUpdated}
      disabled={disabled}
    />
  );
}

function PageStatusControl({ document, page, onUpdated, disabled }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const workflow = workflowOf(document, page);
  const update = async (status) => {
    setBusy(true);
    setError('');
    try {
      onUpdated(await savePageStatus(document.id, page, workflow, status));
    } catch (cause) {
      setError(cause.message);
      // Refresh stale revisions so the next attempt can succeed.
      try {
        onUpdated(await getDocument(document.id));
      } catch {
        /* Keep the original error. */
      }
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="page-status-control">
      <label>
        Trạng thái trang {page}
        <select
          aria-label={`Trạng thái trang ${page}`}
          value={workflow.status}
          disabled={disabled || busy}
          onChange={(event) => update(event.target.value)}
        >
          {Object.entries(PAGE_STATUS_LABELS).map(([id, label]) => (
            <option key={id} value={id}>
              {label}
            </option>
          ))}
        </select>
      </label>
      {busy && <span role="status">Đang lưu…</span>}
      {error && (
        <span className="page-status-error" role="alert">
          {error}
        </span>
      )}
    </div>
  );
}

export default function DrawingPageNavigator({ document, page, onChoose, onUpdated, disabled }) {
  return (
    <DrawingPages
      key={document.id}
      document={document}
      page={page}
      onChoose={onChoose}
      onUpdated={onUpdated}
      disabled={disabled}
    />
  );
}

function DrawingPages({ document, page, onChoose, onUpdated, disabled }) {
  const [filter, setFilter] = useState('all');
  const [pagination, setPagination] = useState({ page, pages: null, offset: 0 });
  const pages = useMemo(
    () =>
      Array.from({ length: document.page_count }, (_, index) => index + 1).filter(
        (number) =>
          filter === 'all' ||
          (filter === 'unfinished'
            ? workflowOf(document, number).status !== 'completed'
            : workflowOf(document, number).status === filter),
      ),
    [document, filter],
  );
  const selectedIndex = pages.indexOf(page);
  const offset =
    (pagination.page !== page || pagination.pages !== pages) && selectedIndex >= 0
      ? Math.floor(selectedIndex / PAGE_SIZE) * PAGE_SIZE
      : pagination.offset;
  const safeOffset = Math.min(
    offset,
    Math.max(0, Math.floor((pages.length - 1) / PAGE_SIZE) * PAGE_SIZE),
  );
  const complete = document.completed_page_count || 0;
  return (
    <section className="drawing-page-navigator" aria-label="Tiến độ và danh sách trang">
      <div className="drawing-page-heading">
        <strong>
          {complete}/{document.page_count} trang hoàn tất
        </strong>
        <progress max={document.page_count} value={complete} aria-label="Tiến độ hoàn tất bản vẽ" />
        <label>
          Lọc trang
          <select
            aria-label="Lọc theo trạng thái trang"
            value={filter}
            onChange={(event) => {
              setFilter(event.target.value);
              setPagination({ page, pages: null, offset: 0 });
            }}
          >
            <option value="all">Tất cả trang</option>
            <option value="unfinished">Chưa hoàn tất</option>
            {Object.entries(PAGE_STATUS_LABELS).map(([id, label]) => (
              <option key={id} value={id}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <button
          disabled={
            disabled || !pages.some((number) => workflowOf(document, number).status !== 'completed')
          }
          onClick={() =>
            onChoose(
              pages.find(
                (number) => number > page && workflowOf(document, number).status !== 'completed',
              ) || pages.find((number) => workflowOf(document, number).status !== 'completed'),
            )
          }
        >
          Đến trang chưa hoàn tất
        </button>
      </div>
      <PageStatusSelect document={document} page={page} onUpdated={onUpdated} disabled={disabled} />
      <div className="drawing-page-thumbnails">
        {pages.slice(safeOffset, safeOffset + PAGE_SIZE).map((number) => {
          const status = workflowOf(document, number).status;
          return (
            <button
              key={`${document.id}-${number}`}
              className={`drawing-page-thumbnail ${number === page ? 'is-selected' : ''}`}
              aria-pressed={number === page}
              disabled={disabled}
              onClick={() => onChoose(number)}
            >
              <img
                src={pageThumbnailUrl(document.id, number)}
                loading="lazy"
                alt={`Xem trước trang ${number}`}
              />
              <strong>Trang {number}</strong>
              <span className={`page-status-badge status-${status}`}>
                {PAGE_STATUS_LABELS[status]}
              </span>
            </button>
          );
        })}
        {!pages.length && <p>Không có trang phù hợp.</p>}
      </div>
      {pages.length > PAGE_SIZE && (
        <div className="drawing-page-pagination">
          <button
            disabled={safeOffset === 0}
            onClick={() => setPagination({ page, pages, offset: safeOffset - PAGE_SIZE })}
          >
            Trước
          </button>
          <span>
            {safeOffset + 1}–{Math.min(safeOffset + PAGE_SIZE, pages.length)} / {pages.length} trang
          </span>
          <button
            disabled={safeOffset + PAGE_SIZE >= pages.length}
            onClick={() => setPagination({ page, pages, offset: safeOffset + PAGE_SIZE })}
          >
            Sau
          </button>
        </div>
      )}
    </section>
  );
}

export function AnnotationPageStatus({ drawing, revision, dirty, busy, hidden }) {
  const [document, setDocument] = useState(null);
  const [error, setError] = useState('');
  const [loadedRequest, setLoadedRequest] = useState(null);
  const requestKey = `${drawing?.id}-${drawing?.page_number || 1}-${revision}-${hidden}`;
  const loading = loadedRequest !== requestKey;
  useEffect(() => {
    if (!drawing || hidden) return undefined;
    let cancelled = false;
    getDocument(drawing.id)
      .then((loaded) => {
        if (!cancelled) {
          setDocument(loaded);
          setError('');
        }
      })
      .catch((cause) => {
        if (!cancelled) setError(cause.message);
      })
      .finally(() => {
        if (!cancelled) setLoadedRequest(requestKey);
      });
    return () => {
      cancelled = true;
    };
  }, [drawing, hidden, requestKey]);
  if (!drawing) return null;
  return (
    <div className="annotation-page-workflow">
      {document?.id === drawing.id && (
        <>
          <PageStatusSelect
            document={document}
            page={drawing.page_number || 1}
            onUpdated={(loaded) =>
              setDocument((current) => (current?.id === loaded.id ? loaded : current))
            }
            disabled={dirty || busy || loading}
          />
          <span>
            {document.completed_page_count}/{document.page_count} trang hoàn tất
          </span>
        </>
      )}
      {dirty && <small>Lưu nhãn trước khi đổi trạng thái.</small>}
      {error && (
        <span className="page-status-error" role="alert">
          {error}
        </span>
      )}
    </div>
  );
}
