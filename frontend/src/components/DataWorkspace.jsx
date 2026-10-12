import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Download,
  FileText,
  ListChecks,
  Maximize2,
  PanelLeft,
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
import { deleteDrawingDocument, organizeDrawingDocument } from '../services/documents';
import DrawingUploadPanel from './DrawingUploadPanel';
import DrawingPageNavigator from './DrawingPageNavigator';

const sizeLabel = (bytes) =>
  bytes < 1024 * 1024 ? `${Math.round(bytes / 1024)} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
const dateLabel = (value) =>
  new Date(value).toLocaleString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh' });
const workspaceTabs = [
  { id: 'drawing', label: 'Bản vẽ', icon: FileText },
  { id: 'upload', label: 'Upload bản vẽ', icon: Upload },
  { id: 'progress', label: 'Trạng thái & tiến độ', icon: ListChecks },
];

function DrawingOrganizationForm({ document, documents, onUpdated, disabled }) {
  const [draft, setDraft] = useState({
    project: document.project || '',
    drawing_set: document.drawing_set || '',
    tags: (document.tags || []).join(', '),
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const save = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    setMessage('');
    try {
      onUpdated(
        await organizeDrawingDocument(document.id, {
          ...draft,
          tags: draft.tags
            .split(',')
            .map((tag) => tag.trim())
            .filter(Boolean),
        }),
      );
      setMessage('Đã lưu nhóm và tag.');
    } catch (cause) {
      setError(cause.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <details className="drawing-organization">
      <summary>
        Nhóm và tag · {document.project || 'Chưa có dự án'}
        {document.drawing_set && ` / ${document.drawing_set}`}
      </summary>
      <form onSubmit={save}>
        <label>
          Dự án
          <input
            list="drawing-project-options"
            maxLength={120}
            value={draft.project}
            disabled={busy || disabled}
            onChange={(event) => setDraft({ ...draft, project: event.target.value })}
            placeholder="VD: Nhà máy A"
          />
        </label>
        <datalist id="drawing-project-options">
          {[...new Set(documents.map((item) => item.project).filter(Boolean))].map((name) => (
            <option key={name} value={name} />
          ))}
        </datalist>
        <label>
          Bộ bản vẽ
          <input
            list="drawing-set-options"
            maxLength={120}
            value={draft.drawing_set}
            disabled={busy || disabled}
            onChange={(event) => setDraft({ ...draft, drawing_set: event.target.value })}
            placeholder="VD: P&ID khu vực 01"
          />
        </label>
        <datalist id="drawing-set-options">
          {[
            ...new Set(
              documents
                .filter((item) => !draft.project || item.project === draft.project)
                .map((item) => item.drawing_set)
                .filter(Boolean),
            ),
          ].map((name) => (
            <option key={name} value={name} />
          ))}
        </datalist>
        <label>
          Tag, cách nhau bằng dấu phẩy
          <input
            value={draft.tags}
            disabled={busy || disabled}
            onChange={(event) => setDraft({ ...draft, tags: event.target.value })}
            placeholder="VD: piping, scan, ưu tiên"
          />
        </label>
        <button disabled={busy || disabled}>{busy ? 'Đang lưu…' : 'Lưu nhóm và tag'}</button>
      </form>
      {error && (
        <p className="data-error" role="alert">
          {error}
        </p>
      )}
      {message && <p role="status">{message}</p>}
    </details>
  );
}

export default function DataWorkspace({
  drawing,
  onDrawingChange,
  isUploading,
  onAnnotate,
  hidden,
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
  const [projectFilter, setProjectFilter] = useState('');
  const [setFilterValue, setSetFilter] = useState('');
  const [tagFilter, setTagFilter] = useState('');
  const [progressFilter, setProgressFilter] = useState('all');
  const [sort, setSort] = useState('updated');
  const [groupBy, setGroupBy] = useState('none');
  const [workspaceTab, setWorkspaceTab] = useState('drawing');
  const [libraryOpen, setLibraryOpen] = useState(!drawing);
  const canvas = useRef(null);
  const viewport = useRef(null);
  const selectionRequest = useRef(0);
  const annotations =
    savedAnnotations?.source.drawing_id === drawing?.id &&
    savedAnnotations?.source.page_number === (drawing?.page_number || 1)
      ? savedAnnotations
      : null;

  useEffect(() => {
    if (hidden) return undefined;
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
  }, [drawing?.id, refresh, hidden]);

  useEffect(() => {
    if (!drawing || hidden) return undefined;
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
  }, [drawing, refresh, hidden]);

  const counts = {
    all: documents.length,
    labeled: documents.filter((item) => item.is_labeled).length,
    unlabeled: documents.filter((item) => !item.is_labeled).length,
  };
  const visibleDocuments = documents
    .filter(
      (item) =>
        [item.name, item.project, item.drawing_set, ...(item.tags || [])]
          .join(' ')
          .toLowerCase()
          .includes(query.trim().toLowerCase()) &&
        (filter === 'all' || (filter === 'labeled' ? item.is_labeled : !item.is_labeled)) &&
        (!projectFilter || item.project === projectFilter) &&
        (!setFilterValue || item.drawing_set === setFilterValue) &&
        (!tagFilter || item.tags?.includes(tagFilter)) &&
        (workspaceTab !== 'progress' ||
          progressFilter === 'all' ||
          (progressFilter === 'completed'
            ? item.completed_page_count === item.page_count
            : item.completed_page_count < item.page_count)),
    )
    .sort((a, b) =>
      sort === 'name'
        ? a.name.localeCompare(b.name, 'vi')
        : new Date(sort === 'created' ? b.created_at : b.updated_at || b.created_at) -
          new Date(sort === 'created' ? a.created_at : a.updated_at || a.created_at),
    );
  const documentGroups = new Map();
  for (const item of visibleDocuments) {
    const group =
      groupBy === 'none'
        ? ''
        : groupBy === 'project'
          ? item.project || 'Chưa có dự án'
          : `${item.project || 'Chưa có dự án'} / ${item.drawing_set || 'Chưa có bộ bản vẽ'}`;
    if (!documentGroups.has(group)) documentGroups.set(group, []);
    documentGroups.get(group).push(item);
  }
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
  const updateCatalogItem = (item) =>
    setDocuments((items) =>
      items.some((existing) => existing.id === item.id)
        ? items.map((existing) => (existing.id === item.id ? item : existing))
        : [item, ...items],
    );

  const choose = async (item, page = 1) => {
    const request = ++selectionRequest.current;
    setPageLoading(true);
    setError('');
    try {
      const loaded = await getDocumentPage(item.id, page);
      if (request === selectionRequest.current) {
        onDrawingChange(loaded);
        setLibraryOpen(false);
      }
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
    <main className="data-workspace" hidden={hidden}>
      <div className="data-heading">
        <div className="data-title">
          <h1>Data</h1>
          <p>Quản lý dữ liệu bản vẽ</p>
        </div>
        <div className="data-workspace-tabs" role="tablist" aria-label="Chế độ Data">
          {workspaceTabs.map(({ id, label, icon: Icon }, index) => (
            <button
              key={id}
              id={`data-tab-${id}`}
              role="tab"
              aria-selected={workspaceTab === id}
              aria-controls={`data-panel-${id}`}
              tabIndex={workspaceTab === id ? 0 : -1}
              onClick={() => setWorkspaceTab(id)}
              onKeyDown={(event) => {
                const next =
                  event.key === 'ArrowRight'
                    ? (index + 1) % workspaceTabs.length
                    : event.key === 'ArrowLeft'
                      ? (index + workspaceTabs.length - 1) % workspaceTabs.length
                      : event.key === 'Home'
                        ? 0
                        : event.key === 'End'
                          ? workspaceTabs.length - 1
                          : null;
                if (next === null) return;
                event.preventDefault();
                setWorkspaceTab(workspaceTabs[next].id);
                event.currentTarget.parentElement.children[next].focus();
              }}
            >
              <Icon size={16} />
              {label}
            </button>
          ))}
        </div>
        <button
          className="data-library-toggle"
          aria-expanded={libraryOpen && workspaceTab !== 'upload'}
          aria-controls="data-library-drawer"
          onClick={() => {
            if (workspaceTab === 'upload') {
              setWorkspaceTab('drawing');
              setLibraryOpen(true);
            } else setLibraryOpen((value) => !value);
          }}
        >
          <PanelLeft size={16} />
          Danh sách bản vẽ <span>{documents.length}</span>
        </button>
      </div>
      {error && (
        <p className="data-error" role="alert">
          {error}
        </p>
      )}
      <div className="data-content">
        {libraryOpen && workspaceTab !== 'upload' && (
          <button
            className="data-library-backdrop"
            aria-label="Đóng bảng danh sách"
            tabIndex={-1}
            onClick={() => setLibraryOpen(false)}
          />
        )}
        <section
          className="data-library"
          id="data-library-drawer"
          aria-label="Danh sách bản vẽ"
          hidden={!libraryOpen || workspaceTab === 'upload'}
          onKeyDown={(event) => {
            if (event.key === 'Escape') setLibraryOpen(false);
          }}
        >
          <div className="data-library-heading">
            <strong>Thư viện bản vẽ</strong>
            <button aria-label="Đóng danh sách bản vẽ" onClick={() => setLibraryOpen(false)}>
              <X size={16} />
            </button>
          </div>
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
                placeholder="Tìm tên, dự án, bộ bản vẽ, tag…"
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
          <details className="data-library-options">
            <summary>
              Bộ lọc & sắp xếp
              {(projectFilter || setFilterValue || tagFilter) && <span>Đang lọc</span>}
            </summary>
            <div className="data-organization-filters">
              <select
                aria-label="Lọc dự án"
                value={projectFilter}
                onChange={(event) => {
                  setProjectFilter(event.target.value);
                  setSetFilter('');
                }}
              >
                <option value="">Tất cả dự án</option>
                {[...new Set(documents.map((item) => item.project).filter(Boolean))]
                  .sort()
                  .map((name) => (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  ))}
              </select>
              <select
                aria-label="Lọc bộ bản vẽ"
                value={setFilterValue}
                onChange={(event) => setSetFilter(event.target.value)}
              >
                <option value="">Tất cả bộ bản vẽ</option>
                {[
                  ...new Set(
                    documents
                      .filter((item) => !projectFilter || item.project === projectFilter)
                      .map((item) => item.drawing_set)
                      .filter(Boolean),
                  ),
                ]
                  .sort()
                  .map((name) => (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  ))}
              </select>
              <select
                aria-label="Lọc tag"
                value={tagFilter}
                onChange={(event) => setTagFilter(event.target.value)}
              >
                <option value="">Tất cả tag</option>
                {[...new Set(documents.flatMap((item) => item.tags || []))].sort().map((tag) => (
                  <option key={tag} value={tag}>
                    {tag}
                  </option>
                ))}
              </select>
              <select
                aria-label="Sắp xếp bản vẽ"
                value={sort}
                onChange={(event) => setSort(event.target.value)}
              >
                <option value="updated">Cập nhật gần nhất</option>
                <option value="created">Upload mới nhất</option>
                <option value="name">Tên A–Z</option>
              </select>
              <select
                aria-label="Nhóm danh sách bản vẽ"
                value={groupBy}
                onChange={(event) => setGroupBy(event.target.value)}
              >
                <option value="none">Không nhóm</option>
                <option value="project">Nhóm theo dự án</option>
                <option value="drawing_set">Nhóm theo dự án / bộ bản vẽ</option>
              </select>
              <button
                onClick={() => {
                  setProjectFilter('');
                  setSetFilter('');
                  setTagFilter('');
                  setProgressFilter('all');
                  setFilter('all');
                  setQuery('');
                }}
              >
                Xóa bộ lọc
              </button>
            </div>
          </details>
          <div className="data-drawing-list" aria-busy={loading}>
            {loading ? (
              <div className="data-empty">Đang tải danh sách…</div>
            ) : visibleDocuments.length ? (
              [...documentGroups].map(([group, items]) => (
                <section key={group} className="data-document-group">
                  {group && (
                    <h3>
                      {group} <span>{items.length} bản vẽ</span>
                    </h3>
                  )}
                  {items.map((item) => (
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
                          <small>Cập nhật {dateLabel(item.updated_at || item.created_at)}</small>
                          {(item.project || item.drawing_set) && (
                            <small>
                              {[item.project, item.drawing_set].filter(Boolean).join(' / ')}
                            </small>
                          )}
                          {item.tags?.length > 0 && (
                            <span className="drawing-tags">
                              {item.tags.map((tag) => (
                                <span key={tag}>{tag}</span>
                              ))}
                            </span>
                          )}
                          <span
                            className={`data-label-badge ${item.is_labeled ? 'is-labeled' : ''}`}
                          >
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
                  ))}
                </section>
              ))
            ) : (
              <div className="data-empty">
                <FileText size={30} />
                <strong>
                  {documents.length ? 'Không tìm thấy bản vẽ phù hợp' : 'Chưa có bản vẽ'}
                </strong>
                <p>
                  {filter === 'labeled'
                    ? 'Các bản vẽ có nhãn đã lưu sẽ xuất hiện tại đây.'
                    : 'Upload bản vẽ hoặc điều chỉnh bộ lọc.'}
                </p>
              </div>
            )}
          </div>
          <p className="data-library-note">
            {visibleDocuments.length}/{documents.length} bản vẽ · Chọn một bản vẽ để mở
          </p>
        </section>
        <section
          className="data-preview"
          ref={viewport}
          id="data-panel-drawing"
          role="tabpanel"
          aria-labelledby="data-tab-drawing"
          hidden={workspaceTab !== 'drawing'}
        >
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
                centerOnResize
                onZoomChange={setZoom}
              />
            </>
          ) : (
            <div className="data-empty">
              <FileText size={42} />
              <strong>Chọn bản vẽ để xem</strong>
              <p>Mở danh sách để chọn bản vẽ, hoặc tải file ở tab Upload bản vẽ.</p>
              <button className="data-library-toggle" onClick={() => setLibraryOpen(true)}>
                <PanelLeft size={16} />
                Chọn bản vẽ từ thư viện
              </button>
            </div>
          )}
        </section>
        <section
          className="data-upload-tab"
          id="data-panel-upload"
          role="tabpanel"
          aria-labelledby="data-tab-upload"
          hidden={workspaceTab !== 'upload'}
        >
          <div className="data-tab-heading">
            <div>
              <h2>Upload bản vẽ</h2>
              <p>Chọn hoặc kéo thả nhiều file để thêm vào thư viện.</p>
            </div>
            <button
              className="data-library-toggle"
              onClick={() => {
                setWorkspaceTab('drawing');
                setLibraryOpen(true);
              }}
            >
              <PanelLeft size={16} />
              Mở thư viện bản vẽ
            </button>
          </div>
          <DrawingUploadPanel
            disabled={isUploading || deleting}
            onUploaded={(item) => {
              updateCatalogItem(item);
              setRefresh((value) => value + 1);
            }}
          />
        </section>
        <section
          className="data-progress-tab"
          id="data-panel-progress"
          role="tabpanel"
          aria-labelledby="data-tab-progress"
          hidden={workspaceTab !== 'progress'}
        >
          <div className="data-tab-heading">
            <div>
              <h2>Trạng thái & tiến độ</h2>
              <p>{drawing ? drawing.name : 'Chọn bản vẽ để quản lý trạng thái từng trang.'}</p>
            </div>
            {drawing && (
              <button className="data-library-toggle" onClick={() => setWorkspaceTab('drawing')}>
                <FileText size={16} />
                Xem bản vẽ
              </button>
            )}
          </div>
          <div className="data-progress-filters">
            <label>
              Tiến độ bản vẽ
              <select
                aria-label="Lọc tiến độ bản vẽ"
                value={progressFilter}
                onChange={(event) => {
                  setProgressFilter(event.target.value);
                  setLibraryOpen(true);
                }}
              >
                <option value="all">Mọi tiến độ</option>
                <option value="unfinished">Chưa hoàn tất</option>
                <option value="completed">Đã hoàn tất</option>
              </select>
            </label>
            <span>
              {documents.filter((item) => item.completed_page_count === item.page_count).length}/
              {documents.length} bản vẽ hoàn tất
            </span>
          </div>
          {drawing ? (
            <>
              <DrawingPageNavigator
                document={selected || drawing}
                page={drawing.page_number || 1}
                onChoose={(page) => choose(drawing, page)}
                onUpdated={updateCatalogItem}
                disabled={pageLoading || deleting}
              />
              <DrawingOrganizationForm
                key={drawing.id}
                document={selected || drawing}
                documents={documents}
                onUpdated={updateCatalogItem}
                disabled={deleting}
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
              <ListChecks size={36} />
              <strong>Chưa chọn bản vẽ</strong>
              <button className="data-library-toggle" onClick={() => setLibraryOpen(true)}>
                Chọn bản vẽ từ thư viện
              </button>
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
