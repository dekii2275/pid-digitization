import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Download,
  FileText,
  Maximize2,
  RefreshCw,
  Search,
  Tags,
  Trash2,
  Upload,
  X,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';
import TiledDrawingCanvas from './TiledDrawingCanvas';
import { getAnnotations, getDocumentPage, getDocuments } from '../services/annotations';
import { deleteDrawingDocument } from '../services/documents';

const sizeLabel = (bytes) =>
  bytes < 1024 * 1024 ? `${Math.round(bytes / 1024)} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
const dateLabel = (value) => new Date(value).toLocaleString('vi-VN');

export default function DataWorkspace({
  drawing,
  onDrawingChange,
  onUpload,
  isUploading,
  onAnnotate,
}) {
  const [documents, setDocuments] = useState([]);
  const [filter, setFilter] = useState('all');
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [refresh, setRefresh] = useState(0);
  const [error, setError] = useState('');
  const [savedAnnotations, setAnnotations] = useState(null);
  const [showLabels, setShowLabels] = useState(true);
  const [pageLoading, setPageLoading] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleteError, setDeleteError] = useState('');
  const [deleting, setDeleting] = useState(false);
  const [zoom, setZoom] = useState(100);
  const canvas = useRef(null);
  const viewport = useRef(null);
  const selectionRequest = useRef(0);
  const annotations =
    savedAnnotations?.source.drawing_id === drawing?.id &&
    savedAnnotations?.source.page_number === (drawing?.page_number || 1)
      ? savedAnnotations
      : null;

  useEffect(() => {
    let cancelled = false;
    getDocuments()
      .then((items) => {
        if (!cancelled) {
          setDocuments(items);
          setError('');
        }
      })
      .catch((cause) => {
        if (!cancelled) setError(cause.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [drawing?.id, refresh]);

  useEffect(() => {
    if (!drawing) return undefined;
    let cancelled = false;
    getAnnotations(drawing.id, drawing.page_number || 1)
      .then((data) => {
        if (!cancelled) setAnnotations(data);
      })
      .catch((cause) => {
        if (!cancelled) setError(cause.message);
      });
    return () => {
      cancelled = true;
    };
  }, [drawing, refresh]);

  const counts = {
    all: documents.length,
    labeled: documents.filter((item) => item.is_labeled).length,
    unlabeled: documents.filter((item) => !item.is_labeled).length,
  };
  const visibleDocuments = documents.filter(
    (item) =>
      item.name.toLowerCase().includes(query.toLowerCase()) &&
      (filter === 'all' || (filter === 'labeled' ? item.is_labeled : !item.is_labeled)),
  );
  const scene = useMemo(
    () =>
      annotations
        ? {
            symbols: annotations.symbols.map((item) => ({ ...item, type: item.label_id })),
            texts: annotations.texts,
            lines: [],
            topology_edges: annotations.relations,
          }
        : null,
    [annotations],
  );
  const selected = documents.find((item) => item.id === drawing?.id);

  const choose = async (item, page = 1) => {
    const request = ++selectionRequest.current;
    setPageLoading(true);
    setError('');
    try {
      const loaded = await getDocumentPage(item.id, page);
      if (request === selectionRequest.current) onDrawingChange(loaded);
    } catch (cause) {
      if (request === selectionRequest.current) setError(cause.message);
    } finally {
      if (request === selectionRequest.current) setPageLoading(false);
    }
  };
  const remove = async () => {
    setDeleting(true);
    try {
      await deleteDrawingDocument(deleteTarget.id);
      if (drawing?.id === deleteTarget.id) onDrawingChange(null);
      try {
        for (let page = 1; page <= deleteTarget.page_count; page++) {
          localStorage.removeItem(`vpi-annotation-${deleteTarget.id}-p${page}`);
        }
      } catch {
        /* Deletion remains successful if browser storage is unavailable. */
      }
      setDocuments((items) => items.filter((item) => item.id !== deleteTarget.id));
      setDeleteTarget(null);
      setError('');
    } catch (cause) {
      setDeleteError(cause.message);
    } finally {
      setDeleting(false);
    }
  };
  const fullscreen = async () => {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await viewport.current?.requestFullscreen();
    } catch {
      setError('Trình duyệt chưa cho phép xem toàn màn hình.');
    }
  };

  return (
    <main className="data-workspace">
      <div className="data-heading">
        <div>
          <h1>Data</h1>
          <p>Quản lý dữ liệu bản vẽ</p>
        </div>
        <label className={`data-upload ${isUploading ? 'is-disabled' : ''}`}>
          <Upload size={16} /> {isUploading ? 'Đang tải bản vẽ…' : 'Upload bản vẽ PDF'}
          <input
            aria-label="Upload bản vẽ PDF"
            type="file"
            accept=".pdf,application/pdf"
            disabled={isUploading || deleting}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) onUpload(file);
              event.target.value = '';
            }}
          />
        </label>
      </div>
      {error && (
        <p className="data-error" role="alert">
          {error}
        </p>
      )}
      <div className="data-content">
        <section className="data-library" aria-label="Danh sách bản vẽ">
          <div className="data-filters" role="tablist" aria-label="Lọc bản vẽ">
            {[
              ['all', 'Tất cả'],
              ['labeled', 'Đã gán nhãn'],
              ['unlabeled', 'Chưa gán nhãn'],
            ].map(([id, label]) => (
              <button
                key={id}
                role="tab"
                aria-selected={filter === id}
                onClick={() => setFilter(id)}
              >
                {label} <span>{counts[id]}</span>
              </button>
            ))}
          </div>
          <div className="data-search">
            <label>
              <Search size={16} />
              <input
                aria-label="Tìm bản vẽ"
                placeholder="Tìm theo tên bản vẽ…"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
            </label>
            <button
              title="Làm mới danh sách"
              aria-label="Làm mới danh sách"
              disabled={isUploading || deleting}
              onClick={() => {
                setLoading(true);
                setRefresh((value) => value + 1);
              }}
            >
              <RefreshCw size={16} />
            </button>
          </div>
          <div className="data-drawing-list" aria-busy={loading}>
            {loading ? (
              <div className="data-empty">Đang tải danh sách…</div>
            ) : visibleDocuments.length ? (
              visibleDocuments.map((item) => (
                <article
                  key={item.id}
                  className={`data-drawing-card ${drawing?.id === item.id ? 'is-selected' : ''}`}
                >
                  <button
                    className="data-drawing-select"
                    disabled={isUploading || deleting}
                    onClick={() => choose(item)}
                  >
                    <FileText size={24} />
                    <div>
                      <strong>{item.name}</strong>
                      <small>
                        {item.source_type.toUpperCase()} · {item.page_count} trang ·{' '}
                        {sizeLabel(item.byte_size)}
                      </small>
                      <small>{dateLabel(item.created_at)}</small>
                      <span className={`data-label-badge ${item.is_labeled ? 'is-labeled' : ''}`}>
                        <Tags size={12} />
                        {item.is_labeled
                          ? `Đã gán nhãn · ${item.annotation_count} nhãn / ${item.labeled_pages.length} trang`
                          : 'Chưa gán nhãn'}
                      </span>
                    </div>
                  </button>
                  <button
                    className="data-delete"
                    aria-label={`Xóa ${item.name}`}
                    title="Xóa bản vẽ"
                    disabled={deleting || isUploading || pageLoading}
                    onClick={() => {
                      setDeleteError('');
                      setDeleteTarget(item);
                    }}
                  >
                    <Trash2 size={16} />
                  </button>
                </article>
              ))
            ) : (
              <div className="data-empty">
                <FileText size={30} />
                <strong>
                  {query || filter !== 'all' ? 'Không tìm thấy bản vẽ phù hợp' : 'Chưa có bản vẽ'}
                </strong>
                <p>
                  {filter === 'labeled'
                    ? 'Các bản vẽ có nhãn đã lưu sẽ xuất hiện tại đây.'
                    : 'Upload bản vẽ PDF để bắt đầu.'}
                </p>
              </div>
            )}
          </div>
          <p className="data-library-note">PDF tối đa 100 MB · Hỗ trợ nhiều trang</p>
        </section>
        <section className="data-preview" ref={viewport} aria-label="Xem bản vẽ">
          {drawing ? (
            <>
              <div className="data-preview-toolbar">
                <strong title={drawing.name}>{drawing.name}</strong>
                <select
                  aria-label="Trang bản vẽ"
                  value={drawing.page_number || 1}
                  disabled={pageLoading || isUploading || deleting}
                  onChange={(event) => choose(drawing, Number(event.target.value))}
                >
                  {Array.from({ length: drawing.page_count }, (_, index) => (
                    <option key={index + 1} value={index + 1}>
                      Trang {index + 1}/{drawing.page_count}
                    </option>
                  ))}
                </select>
                <button
                  disabled={pageLoading || isUploading || deleting || !annotations}
                  onClick={() => onAnnotate(drawing)}
                >
                  <Tags size={14} />
                  Gán nhãn
                </button>
                <a href={drawing.original_url} download>
                  <Download size={14} />
                  File gốc
                </a>
              </div>
              <div className="data-preview-controls">
                <label>
                  <input
                    type="checkbox"
                    checked={showLabels}
                    onChange={(event) => setShowLabels(event.target.checked)}
                  />
                  Hiện nhãn đã lưu
                </label>
                <span>
                  {pageLoading
                    ? 'Đang tải trang…'
                    : `${annotations?.symbols.length || 0} symbol · ${annotations?.texts.length || 0} OCR · ${annotations?.relations.length || 0} quan hệ`}
                </span>
                <button
                  aria-label="Căn vừa bản vẽ"
                  title="Căn vừa bản vẽ"
                  onClick={() => canvas.current?.fit()}
                >
                  ⌖
                </button>
                <button aria-label="Thu nhỏ bản vẽ" onClick={() => canvas.current?.zoomOut()}>
                  <ZoomOut size={15} />
                </button>
                <span>{zoom}%</span>
                <button aria-label="Phóng to bản vẽ" onClick={() => canvas.current?.zoomIn()}>
                  <ZoomIn size={15} />
                </button>
                <button aria-label="Toàn màn hình" onClick={fullscreen}>
                  <Maximize2 size={15} />
                </button>
              </div>
              <TiledDrawingCanvas
                key={`${drawing.id}-${drawing.page_number || 1}`}
                ref={canvas}
                drawing={drawing}
                results={scene}
                showDetections={showLabels}
                showTags={showLabels}
                showConnections={showLabels}
                panOnly
                onZoomChange={setZoom}
              />
              {selected?.is_labeled && (
                <div className="data-preview-summary">
                  Trang đã gán nhãn: {selected.labeled_pages.join(', ')} · Lưu gần nhất:{' '}
                  {dateLabel(selected.last_labeled_at)}
                </div>
              )}
            </>
          ) : (
            <div className="data-empty">
              <FileText size={42} />
              <strong>Chọn bản vẽ để xem</strong>
              <p>Xem từng trang PDF và các nhãn đã lưu.</p>
            </div>
          )}
        </section>
      </div>
      {deleteTarget && (
        <div className="data-dialog-backdrop">
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="data-delete-title"
            className="data-delete-dialog"
          >
            <button
              className="data-dialog-close"
              aria-label="Đóng xác nhận xóa"
              disabled={deleting}
              onClick={() => setDeleteTarget(null)}
            >
              <X size={18} />
            </button>
            <h2 id="data-delete-title">Xóa bản vẽ?</h2>
            <p>
              <strong>{deleteTarget.name}</strong>
            </p>
            <p>File gốc, nhãn và dữ liệu xử lý của bản vẽ sẽ bị xóa.</p>
            {deleteError && (
              <p className="data-error" role="alert">
                {deleteError}
              </p>
            )}
            <div>
              <button autoFocus disabled={deleting} onClick={() => setDeleteTarget(null)}>
                Hủy
              </button>
              <button className="data-confirm-delete" disabled={deleting} onClick={remove}>
                {deleting ? 'Đang xóa…' : 'Xóa bản vẽ'}
              </button>
            </div>
          </section>
        </div>
      )}
    </main>
  );
}
