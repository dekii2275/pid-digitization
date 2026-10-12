import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Check,
  CheckCircle2,
  Download,
  FolderOpen,
  Hand,
  Maximize2,
  MousePointer2,
  Redo2,
  Save,
  Scan,
  Search,
  Share2,
  SquareDashedMousePointer,
  Trash2,
  Type,
  Undo2,
  Upload,
  X,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';
import TiledDrawingCanvas from './TiledDrawingCanvas';
import { AnnotationPageStatus } from './DrawingPageNavigator';
import SymbolPreview from './SymbolPreview';
import ExistingDrawingPicker from './ExistingDrawingPicker';
import { getSymbolLibrary } from '../services/symbolLibrary';
import {
  exportDataset,
  getAnnotations,
  getDocumentPage,
  getDocuments,
  saveAnnotations,
} from '../services/annotations';

const modes = [
  { id: 'symbol', label: 'Detect symbol', icon: Scan },
  { id: 'text', label: 'Detect text OCR', icon: Type },
  { id: 'relation', label: 'Detect quan hệ', icon: Share2 },
];
const collections = { symbol: 'symbols', text: 'texts', relation: 'relations' };
const snapshot = (data) =>
  structuredClone({ symbols: data.symbols, texts: data.texts, relations: data.relations });
const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
const draftKey = (drawing) => `vpi-annotation-${drawing.id}-p${drawing.page_number || 1}`;
const readLocal = (key) => {
  try {
    return JSON.parse(localStorage.getItem(key));
  } catch {
    return null;
  }
};
const writeLocal = (key, value) => {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* Server saving remains available if browser storage is full. */
  }
};

function DocumentPicker({ drawing, documents, onChoose, onUpload, isUploading }) {
  return (
    <section className="annotation-document">
      <h3>Bản vẽ hiện tại</h3>
      <strong className="annotation-document-name" title={drawing?.name}>
        {drawing?.name || 'Chưa chọn bản vẽ'}
      </strong>
      {drawing && (
        <div className="annotation-document-page">
          <label className="annotation-field">
            <span>Trang đang gán nhãn</span>
            <select
              aria-label="Trang PDF / ảnh"
              value={drawing.page_number || 1}
              disabled={isUploading}
              onChange={(event) => onChoose(drawing.id, Number(event.target.value))}
            >
              {Array.from({ length: drawing.page_count }, (_, index) => (
                <option key={index + 1} value={index + 1}>
                  Trang {index + 1} / {drawing.page_count}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}
      <details className="annotation-document-options" open={!drawing}>
        <summary>Đổi nhanh / tải bản vẽ mới</summary>
        <label className="annotation-field">
          <span>Bản vẽ có sẵn</span>
          <select
            aria-label="Bản vẽ đã tải"
            value={drawing?.id || ''}
            disabled={isUploading}
            onChange={(event) => {
              if (event.target.value) onChoose(event.target.value, 1);
            }}
          >
            <option value="">Chọn bản vẽ</option>
            {documents.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
        <label className="annotation-upload">
          <Upload size={15} /> {isUploading ? 'Đang chuẩn bị ảnh…' : 'Tải ảnh / PDF mới'}
          <input
            aria-label="Tải bản vẽ gán nhãn"
            type="file"
            accept=".png,.jpg,.jpeg,.pdf"
            disabled={isUploading}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) onUpload(file);
              event.target.value = '';
            }}
          />
        </label>
        {drawing && (
          <small>
            {drawing.width} × {drawing.height} px
            {drawing.source_type === 'pdf' && ` · ${drawing.render_dpi || 144} DPI`}
          </small>
        )}
      </details>
    </section>
  );
}

function AnnotationPage({
  drawing,
  mode,
  catalog,
  documents,
  onChoose,
  onUpload,
  isUploading,
  hidden,
}) {
  const [data, setData] = useState(null);
  const dataRef = useRef(null);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [saveNotice, setSaveNotice] = useState(null);
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('All');
  const [labelCode, setLabelCode] = useState('');
  const [selection, setSelection] = useState(null);
  const [tool, setTool] = useState('select');
  const [relationType, setRelationType] = useState('connected_to');
  const [relationSource, setRelationSource] = useState('');
  const [relationTarget, setRelationTarget] = useState('');
  const [zoom, setZoom] = useState(100);
  const [history, setHistory] = useState({ undo: 0, redo: 0 });
  const past = useRef([]),
    future = useRef([]),
    dragSnapshot = useRef(null),
    canvas = useRef(null);
  const page = drawing?.page_number || 1;
  const syncHistory = () => setHistory({ undo: past.current.length, redo: future.current.length });
  const adopt = (value) => {
    dataRef.current = value;
    setData(value);
  };

  useEffect(() => {
    if (!drawing || hidden) return undefined;
    let cancelled = false;
    getAnnotations(drawing.id, page)
      .then((saved) => {
        if (cancelled) return;
        const local = readLocal(draftKey(drawing));
        const restore = local?.dirty && local.data?.revision === saved.revision;
        const value = restore ? { ...saved, ...snapshot(local.data) } : saved;
        dataRef.current = value;
        setData(value);
        setDirty(Boolean(restore));
        if (restore) setMessage('Đã khôi phục bản nháp chưa lưu trên trình duyệt.');
        else if (local?.dirty) {
          writeLocal(`${draftKey(drawing)}-backup`, local);
          setMessage(
            'Bản nháp cũ khác phiên bản máy chủ. Đang hiển thị bản đã lưu; bản nháp cũ vẫn ở bộ nhớ trình duyệt.',
          );
        }
      })
      .catch((cause) => {
        if (!cancelled) setError(cause.message);
      });
    return () => {
      cancelled = true;
    };
  }, [drawing, page, hidden]);
  useEffect(() => {
    if (data && drawing) writeLocal(draftKey(drawing), { data, dirty });
  }, [data, dirty, drawing]);
  useEffect(() => {
    if (!saveNotice || hidden) return undefined;
    const timer = window.setTimeout(() => setSaveNotice(null), 5000);
    return () => window.clearTimeout(timer);
  }, [saveNotice, hidden]);
  useEffect(() => {
    const warn = (event) => {
      if (dirty) {
        event.preventDefault();
        event.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);

  const mutate = (change) => {
    const current = dataRef.current;
    if (!current || busy) return;
    if (!dragSnapshot.current) {
      past.current.push(snapshot(current));
      past.current = past.current.slice(-50);
      future.current = [];
    }
    adopt(change(current));
    setDirty(true);
    setError('');
    setMessage('');
    syncHistory();
  };
  const undo = (redo = false) => {
    const from = redo ? future : past,
      to = redo ? past : future;
    if (!from.current.length || busy || !dataRef.current) return;
    to.current.push(snapshot(dataRef.current));
    adopt({ ...dataRef.current, ...from.current.pop() });
    setDirty(true);
    setSelection(null);
    syncHistory();
  };
  const endDrag = () => {
    if (
      dragSnapshot.current &&
      JSON.stringify(dragSnapshot.current) !== JSON.stringify(snapshot(dataRef.current))
    ) {
      past.current.push(dragSnapshot.current);
      past.current = past.current.slice(-50);
      future.current = [];
    }
    dragSnapshot.current = null;
    syncHistory();
  };
  const chooseTool = (next) => {
    canvas.current?.cancelDrawing();
    setTool(next);
  };
  const currentTool = mode === 'relation' && tool === 'draw' ? 'select' : tool;
  const classes = data?.classes || [];
  const classMap = new Map(classes.map((item) => [item.code, item]));
  const enabled = new Map(catalog.filter((item) => item.enabled).map((item) => [item.code, item]));
  const library = classes.filter(
    (item) =>
      enabled.has(item.code) &&
      (category === 'All' || item.category === category) &&
      `${item.code} ${item.name}`.toLowerCase().includes(query.trim().toLowerCase()),
  );
  const selected =
    selection && data?.[collections[selection.kind]]?.find((item) => item.id === selection.id);
  const itemName = (item) => item.label_id || item.text || item.id;
  const normalizeBox = (item, patch) => {
    const merged = { ...item, ...patch };
    const width = clamp(Number(merged.width) || 1, 1, drawing.width);
    const height = clamp(Number(merged.height) || 1, 1, drawing.height);
    return {
      ...merged,
      width,
      height,
      x: clamp(Number(merged.x) || 0, 0, drawing.width - width),
      y: clamp(Number(merged.y) || 0, 0, drawing.height - height),
    };
  };
  const update = (kind, id, patch) =>
    mutate((current) => ({
      ...current,
      [collections[kind]]: current[collections[kind]].map((item) =>
        item.id === id ? normalizeBox(item, patch) : item,
      ),
    }));
  const create = (kind, box) => {
    if (kind === 'symbol' && !classMap.has(labelCode)) {
      setError('Chọn nhãn symbol trong thư viện trước khi khoanh.');
      return;
    }
    const id = crypto.randomUUID();
    mutate((current) => ({
      ...current,
      [collections[kind]]: [
        ...current[collections[kind]],
        { id, ...box, ...(kind === 'symbol' ? { label_id: labelCode } : { text: '' }) },
      ],
    }));
    setSelection({ kind, id });
    setTool('select');
  };
  const remove = () => {
    if (!selected) return;
    mutate((current) => ({
      ...current,
      [collections[selection.kind]]: current[collections[selection.kind]].filter(
        (item) => item.id !== selection.id,
      ),
      relations:
        selection.kind === 'relation'
          ? current.relations.filter((item) => item.id !== selection.id)
          : current.relations.filter(
              (item) => item.source !== selection.id && item.target !== selection.id,
            ),
    }));
    if (relationSource === selection.id) setRelationSource('');
    if (relationTarget === selection.id) setRelationTarget('');
    setSelection(null);
  };
  const save = async (download = false) => {
    if (!dataRef.current || busy) return;
    setBusy(true);
    setError('');
    setSaveNotice(null);
    try {
      const saved = await saveAnnotations(drawing.id, page, dataRef.current);
      adopt(saved);
      setDirty(false);
      writeLocal(draftKey(drawing), { data: saved, dirty: false });
      setSaveNotice({
        savedAt: saved.saved_at,
        symbols: saved.symbols.length,
        texts: saved.texts.length,
        relations: saved.relations.length,
      });
      if (download) await exportDataset(drawing.id, page);
    } catch (cause) {
      setError(cause.message);
    } finally {
      setBusy(false);
    }
  };
  const reload = async () => {
    setBusy(true);
    setError('');
    try {
      const saved = await getAnnotations(drawing.id, page);
      writeLocal(`${draftKey(drawing)}-backup`, { data: dataRef.current, dirty });
      if (dataRef.current) past.current.push(snapshot(dataRef.current));
      adopt(saved);
      setDirty(false);
      setSelection(null);
      syncHistory();
      setMessage('Đã tải bản máy chủ. Có thể Hoàn tác để lấy lại nội dung trước đó.');
    } catch (cause) {
      setError(cause.message);
    } finally {
      setBusy(false);
    }
  };
  const addRelation = (event) => {
    event.preventDefault();
    if (!relationSource || !relationTarget || relationSource === relationTarget) {
      setError('Chọn hai đối tượng khác nhau để tạo quan hệ.');
      return;
    }
    if (
      data.relations.some(
        (item) =>
          item.source === relationSource &&
          item.target === relationTarget &&
          item.type === relationType,
      )
    ) {
      setError('Quan hệ này đã tồn tại.');
      return;
    }
    const id = crypto.randomUUID();
    mutate((current) => ({
      ...current,
      relations: [
        ...current.relations,
        { id, source: relationSource, target: relationTarget, type: relationType },
      ],
    }));
    setSelection({ kind: 'relation', id });
    setRelationSource('');
    setRelationTarget('');
  };
  const select = (item) => {
    setSelection({ kind: item.kind === 'connection' ? 'relation' : item.kind, id: item.id });
    if (mode === 'relation' && item.kind !== 'connection') {
      const isSource = relationType === 'text_of' ? item.kind === 'text' : item.kind === 'symbol';
      if (!relationSource && isSource) setRelationSource(item.id);
      else if (item.kind === 'symbol' && relationSource !== item.id) setRelationTarget(item.id);
    }
  };
  const renderScene = data
    ? {
        symbols: data.symbols.map((item) => ({ ...item, type: item.label_id })),
        texts: data.texts,
        lines: [],
        topology_edges: data.relations,
      }
    : null;
  const nodes = [...(data?.symbols || []), ...(data?.texts || [])];
  const sourceOptions = relationType === 'text_of' ? data?.texts || [] : data?.symbols || [];
  const hint =
    currentTool === 'draw'
      ? 'Kéo chuột để khoanh vùng · Lăn chuột để zoom · Esc để hủy khoanh'
      : mode === 'relation'
        ? 'Chọn hai đối tượng hoặc dùng danh sách để nối quan hệ'
        : 'Chọn vùng để kéo/sửa kích thước · Kéo nền để pan · Lăn chuột để zoom';
  const symbolPreview = enabled.get(labelCode);

  return (
    <div
      className="annotation-workspace"
      onKeyDown={(event) => {
        if (event.key === 'Escape') {
          chooseTool('select');
          setSelection(null);
          return;
        }
        if (event.target.closest('input,textarea,select')) return;
        if (event.key === 'Delete' && selected) {
          event.preventDefault();
          remove();
        }
        if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z') {
          event.preventDefault();
          undo(event.shiftKey);
        }
      }}
    >
      <aside className="annotation-sidebar">
        <DocumentPicker
          drawing={drawing}
          documents={documents}
          onChoose={onChoose}
          onUpload={onUpload}
          isUploading={isUploading}
        />
        {mode === 'symbol' && (
          <section className="annotation-library">
            <div className="annotation-section-heading">
              <h3>Thư viện nhãn symbol</h3>
              <span>{classes.filter((item) => enabled.has(item.code)).length} nhãn</span>
            </div>
            {symbolPreview ? (
              <div
                className="annotation-active-label"
                title={`${symbolPreview.code} · ${symbolPreview.name}`}
              >
                <span className="annotation-label-preview">
                  <SymbolPreview symbol={symbolPreview} compact />
                </span>
                <span>
                  <small>Nhãn đang dùng</small>
                  <b>{symbolPreview.code}</b>
                  <span className="annotation-label-name">{symbolPreview.name}</span>
                </span>
                <CheckCircle2 size={17} />
              </div>
            ) : (
              <p className="annotation-library-hint">Chọn một nhãn bên dưới để bắt đầu.</p>
            )}
            {symbolPreview && (
              <p className="annotation-library-hint">
                {currentTool === 'draw'
                  ? 'Kéo trên bản vẽ để khoanh symbol theo nhãn này.'
                  : 'Bấm Khoanh vùng để thêm symbol theo nhãn này.'}
              </p>
            )}
            <label className="annotation-search">
              <Search size={14} />
              <input
                aria-label="Tìm nhãn symbol"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Tìm mã hoặc tên nhãn"
              />
            </label>
            <select
              aria-label="Nhóm nhãn symbol"
              value={category}
              onChange={(event) => setCategory(event.target.value)}
            >
              <option value="All">Tất cả nhóm</option>
              {[...new Set(classes.map((item) => item.category))].map((item) => (
                <option key={item}>{item}</option>
              ))}
            </select>
            <div className="annotation-library-count">{library.length} nhãn phù hợp</div>
            <div className="annotation-label-list" aria-label="Danh sách nhãn symbol">
              {library.map((item) => (
                <button
                  type="button"
                  key={item.code}
                  aria-pressed={item.code === labelCode}
                  title={`${item.code} · ${item.name}`}
                  disabled={busy}
                  onClick={() => {
                    setLabelCode(item.code);
                    chooseTool('draw');
                  }}
                >
                  <span className="annotation-label-preview">
                    <SymbolPreview symbol={enabled.get(item.code)} compact />
                  </span>
                  <span>
                    <b>{item.code}</b>
                    <small>{item.name}</small>
                  </span>
                  {item.code === labelCode && <Check size={16} />}
                </button>
              ))}
              {drawing && !library.length && <p>Không có nhãn phù hợp.</p>}
            </div>
          </section>
        )}
        {mode === 'text' && (
          <section className="annotation-section">
            <h3>Gán nhãn text OCR</h3>
            <p>Khoanh vùng chữ, sau đó nhập nguyên văn nội dung để tạo dữ liệu OCR.</p>
            <button type="button" disabled={!data || busy} onClick={() => chooseTool('draw')}>
              <SquareDashedMousePointer size={14} /> Khoanh vùng chữ
            </button>
          </section>
        )}
        {mode === 'relation' && (
          <section className="annotation-section">
            <h3>Gán nhãn quan hệ</h3>
            <p>Nối hai symbol, hoặc nối vùng OCR với symbol tương ứng.</p>
            <form onSubmit={addRelation}>
              <label className="annotation-field">
                <span>Loại quan hệ</span>
                <select
                  aria-label="Loại quan hệ"
                  value={relationType}
                  onChange={(event) => {
                    setRelationType(event.target.value);
                    setRelationSource('');
                    setRelationTarget('');
                  }}
                >
                  <option value="connected_to">Kết nối</option>
                  <option value="flow_to">Hướng dòng chảy</option>
                  <option value="text_of">Text của symbol</option>
                </select>
              </label>
              <label className="annotation-field">
                <span>Đối tượng nguồn</span>
                <select
                  aria-label="Đối tượng nguồn"
                  value={relationSource}
                  onChange={(event) => setRelationSource(event.target.value)}
                >
                  <option value="">Chọn nguồn</option>
                  {sourceOptions.map((item) => (
                    <option key={item.id} value={item.id}>
                      {itemName(item)} · {item.id.slice(0, 6)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="annotation-field">
                <span>Symbol đích</span>
                <select
                  aria-label="Symbol đích"
                  value={relationTarget}
                  onChange={(event) => setRelationTarget(event.target.value)}
                >
                  <option value="">Chọn đích</option>
                  {(data?.symbols || [])
                    .filter((item) => item.id !== relationSource)
                    .map((item) => (
                      <option key={item.id} value={item.id}>
                        {itemName(item)} · {item.id.slice(0, 6)}
                      </option>
                    ))}
                </select>
              </label>
              <button disabled={!relationSource || !relationTarget || busy}>
                <Share2 size={14} /> Thêm quan hệ
              </button>
            </form>
          </section>
        )}
        {data && (
          <details className="annotation-section annotation-assigned">
            <summary>
              Vùng đã gán nhãn <span>{data[collections[mode]].length}</span>
            </summary>
            <div className="annotation-item-list">
              {data[collections[mode]].map((item, index) => (
                <button
                  type="button"
                  key={item.id}
                  aria-pressed={selection?.id === item.id}
                  onClick={() => {
                    setSelection({ kind: mode, id: item.id });
                    chooseTool('select');
                  }}
                >
                  {index + 1}.{' '}
                  {mode === 'relation'
                    ? `${item.type} · ${item.source.slice(0, 6)} → ${item.target.slice(0, 6)}`
                    : itemName(item)}
                </button>
              ))}
            </div>
          </details>
        )}
      </aside>
      <section className="annotation-canvas-pane">
        <div className="annotation-actions">
          <div>
            {[
              { id: 'select', label: 'Chọn / sửa', icon: MousePointer2 },
              { id: 'draw', label: 'Khoanh vùng', icon: SquareDashedMousePointer },
              { id: 'pan', label: 'Di chuyển ảnh', icon: Hand },
            ]
              .filter((item) => mode !== 'relation' || item.id !== 'draw')
              .map(({ id, label, icon: Icon }) => (
                <button
                  type="button"
                  key={id}
                  aria-pressed={currentTool === id}
                  disabled={!data || busy || (id === 'draw' && mode === 'symbol' && !labelCode)}
                  onClick={() => chooseTool(id)}
                >
                  <Icon size={15} />
                  {label}
                </button>
              ))}
            <button
              type="button"
              title="Hoàn tác"
              disabled={!history.undo || busy}
              onClick={() => undo()}
            >
              <Undo2 size={15} />
            </button>
            <button
              type="button"
              title="Làm lại"
              disabled={!history.redo || busy}
              onClick={() => undo(true)}
            >
              <Redo2 size={15} />
            </button>
          </div>
          <div>
            <span className={`annotation-save-state ${dirty ? 'is-dirty' : ''}`}>
              {busy
                ? 'Đang xử lý…'
                : dirty
                  ? 'Có thay đổi chưa lưu'
                  : data?.saved_at
                    ? 'Đã lưu'
                    : 'Chưa có thay đổi'}
            </span>
            <button
              className="annotation-save-button"
              type="button"
              disabled={!data || busy}
              onClick={() => save()}
            >
              <Save size={14} />
              {busy ? 'Đang lưu…' : 'Lưu nhãn'}
            </button>
            <button type="button" disabled={!data || busy} onClick={() => save(true)}>
              <Download size={14} />
              Xuất dataset
            </button>
          </div>
        </div>
        <AnnotationPageStatus
          drawing={drawing}
          revision={data?.revision}
          dirty={dirty}
          busy={busy}
          hidden={hidden}
        />
        {error && (
          <div className="annotation-notice is-error" role="alert">
            {error}
            {drawing && (
              <button type="button" disabled={busy} onClick={reload}>
                Tải bản máy chủ
              </button>
            )}
          </div>
        )}
        {message && (
          <div className="annotation-notice" role="status">
            {message}
          </div>
        )}
        <div className="annotation-canvas-viewport">
          {saveNotice && !hidden && (
            <div
              className="annotation-save-toast"
              role="status"
              aria-live="polite"
              aria-atomic="true"
            >
              <CheckCircle2 size={22} />
              <div>
                <strong>Lưu nhãn thành công</strong>
                <span>
                  Trang {page} · {saveNotice.symbols} symbol · {saveNotice.texts} OCR ·{' '}
                  {saveNotice.relations} quan hệ
                </span>
              </div>
              <button
                type="button"
                aria-label="Đóng thông báo lưu"
                onClick={() => setSaveNotice(null)}
              >
                <X size={16} />
              </button>
            </div>
          )}
          {!drawing ? (
            <div className="annotation-empty">
              <Scan size={38} />
              <h2>Gán nhãn dữ liệu P&amp;ID</h2>
              <p>Tải ảnh hoặc PDF để bắt đầu khoanh symbol. Không cần chạy pipeline AI.</p>
            </div>
          ) : !data ? (
            <div className="annotation-empty">
              <p>{error ? 'Chưa tải được dữ liệu gán nhãn.' : 'Đang tải dữ liệu gán nhãn…'}</p>
            </div>
          ) : (
            <TiledDrawingCanvas
              ref={canvas}
              drawing={drawing}
              results={renderScene}
              reviewMode
              showBoxLabels={false}
              selectedItem={
                selection?.kind === 'relation' ? { ...selection, kind: 'connection' } : selection
              }
              onSelectItem={select}
              onUpdateItem={update}
              onCreateItem={create}
              drawMode={currentTool === 'draw' && !busy ? mode : null}
              panOnly={currentTool === 'pan' || busy}
              showConnections={mode === 'relation'}
              onZoomChange={setZoom}
              viewerHint={hint}
              onEditStart={() => {
                dragSnapshot.current = snapshot(dataRef.current);
              }}
              onEditEnd={endDrag}
            />
          )}
          {selected && (
            <section
              className="annotation-section annotation-properties annotation-properties-popup"
              role="dialog"
              aria-modal="false"
              aria-labelledby="annotation-properties-title"
            >
              <h3>
                <span id="annotation-properties-title">Thông tin vùng chọn</span>
                <span className="annotation-properties-controls">
                  <button type="button" title="Xóa vùng gán nhãn" disabled={busy} onClick={remove}>
                    <Trash2 size={14} />
                  </button>
                  <button
                    type="button"
                    className="annotation-properties-close"
                    title="Đóng thông tin vùng chọn"
                    aria-label="Đóng thông tin vùng chọn"
                    onClick={() => setSelection(null)}
                  >
                    <X size={16} />
                  </button>
                </span>
              </h3>
              {selection.kind === 'symbol' && (
                <label className="annotation-field">
                  <span>Nhãn của vùng chọn</span>
                  <select
                    aria-label="Nhãn của vùng chọn"
                    value={selected.label_id}
                    disabled={busy}
                    onChange={(event) =>
                      update('symbol', selected.id, { label_id: event.target.value })
                    }
                  >
                    {classes.map((item) => (
                      <option key={item.code} value={item.code}>
                        {item.code} · {item.name}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              {selection.kind === 'text' && (
                <label className="annotation-field">
                  <span>Nội dung OCR</span>
                  <textarea
                    aria-label="Nội dung OCR"
                    value={selected.text}
                    disabled={busy}
                    onChange={(event) => update('text', selected.id, { text: event.target.value })}
                  />
                </label>
              )}
              {selection.kind !== 'relation' && (
                <div className="annotation-coordinates">
                  {['x', 'y', 'width', 'height'].map((field) => (
                    <label key={field}>
                      <span>
                        {field === 'width'
                          ? 'Rộng'
                          : field === 'height'
                            ? 'Cao'
                            : field.toUpperCase()}{' '}
                        (px)
                      </span>
                      <input
                        type="number"
                        min={field === 'x' || field === 'y' ? 0 : 1}
                        step="0.1"
                        value={Math.round(selected[field] * 10) / 10}
                        disabled={busy}
                        onChange={(event) =>
                          update(selection.kind, selected.id, {
                            [field]: Number(event.target.value),
                          })
                        }
                      />
                    </label>
                  ))}
                </div>
              )}
              {selection.kind === 'relation' && (
                <p>
                  {nodes.find((item) => item.id === selected.source)?.label_id ||
                    nodes.find((item) => item.id === selected.source)?.text}{' '}
                  → {nodes.find((item) => item.id === selected.target)?.label_id} · {selected.type}
                </p>
              )}
            </section>
          )}
        </div>
        <div className="annotation-status">
          <span>
            {data
              ? `${data.symbols.length} symbol · ${data.texts.length} OCR · ${data.relations.length} quan hệ`
              : 'Chưa có bản vẽ'}
          </span>
          <span>
            {dirty
              ? 'Bản nháp · chưa lưu máy chủ'
              : data?.saved_at
                ? `Đã lưu lúc ${new Date(data.saved_at).toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' })}`
                : 'Chưa gán nhãn'}
          </span>
          <div>
            <button
              type="button"
              title="Vừa khung"
              disabled={!data}
              onClick={() => canvas.current?.fit()}
            >
              <Maximize2 size={14} />
            </button>
            <button
              type="button"
              title="Thu nhỏ"
              disabled={!data}
              onClick={() => canvas.current?.zoomOut()}
            >
              <ZoomOut size={14} />
            </button>
            <span>{zoom}%</span>
            <button
              type="button"
              title="Phóng to"
              disabled={!data}
              onClick={() => canvas.current?.zoomIn()}
            >
              <ZoomIn size={14} />
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}

export default function GenerateDataWorkspace({
  drawing,
  onDrawingChange,
  onUpload,
  isUploading,
  hidden,
}) {
  const [mode, setMode] = useState('symbol');
  const [documents, setDocuments] = useState([]);
  const [catalog, setCatalog] = useState([]);
  const [error, setError] = useState('');
  const [pickerOpen, setPickerOpen] = useState(false);
  const [choosing, setChoosing] = useState(false);
  const selectionRequest = useRef(0);
  useEffect(() => {
    if (hidden) return undefined;
    let cancelled = false;
    Promise.all([getDocuments(), getSymbolLibrary()])
      .then(async ([loadedDocuments, labels]) => {
        if (cancelled) return;
        setDocuments(loadedDocuments);
        setCatalog(labels);
        setError('');
        const remembered = readLocal('vpi-annotation-last-document');
        if (!drawing && remembered && loadedDocuments.some((item) => item.id === remembered.id)) {
          const restored = await getDocumentPage(remembered.id, remembered.page);
          if (!cancelled) onDrawingChange(restored);
        }
      })
      .catch((cause) => {
        if (!cancelled) setError(cause.message);
      });
    return () => {
      cancelled = true;
    };
  }, [hidden, drawing, onDrawingChange]);
  useEffect(() => {
    if (drawing)
      writeLocal('vpi-annotation-last-document', {
        id: drawing.id,
        page: drawing.page_number || 1,
      });
  }, [drawing]);
  const availableDocuments = useMemo(
    () =>
      drawing && !documents.some((item) => item.id === drawing.id)
        ? [drawing, ...documents]
        : documents,
    [drawing, documents],
  );
  const choose = async (id, page) => {
    const request = ++selectionRequest.current;
    setChoosing(true);
    try {
      const loaded = await getDocumentPage(id, page);
      if (request !== selectionRequest.current) return false;
      onDrawingChange(loaded);
      setError('');
      return true;
    } catch (cause) {
      if (request === selectionRequest.current) setError(cause.message);
      return false;
    } finally {
      if (request === selectionRequest.current) setChoosing(false);
    }
  };
  return (
    <main className="generate-data-shell" hidden={hidden}>
      <div className="generate-data-drawing-actions">
        <span>
          {drawing ? `Đang chỉnh sửa: ${drawing.name}` : 'Chọn bản vẽ để bắt đầu gán nhãn'}
        </span>
        <button
          className="annotation-browse"
          disabled={isUploading || choosing}
          onClick={() => setPickerOpen(true)}
        >
          <FolderOpen size={16} /> Chọn bản vẽ từ Data
        </button>
      </div>
      <div className="generate-data-modes" role="tablist" aria-label="Loại dữ liệu gán nhãn">
        {modes.map(({ id, label, icon: Icon }) => (
          <button
            type="button"
            role="tab"
            key={id}
            id={`annotation-tab-${id}`}
            aria-selected={mode === id}
            aria-controls="annotation-panel"
            onClick={() => setMode(id)}
          >
            <Icon size={17} />
            {label}
          </button>
        ))}
      </div>
      {error && (
        <p className="annotation-notice is-error" role="alert">
          {error}
        </p>
      )}
      <div
        id="annotation-panel"
        role="tabpanel"
        aria-labelledby={`annotation-tab-${mode}`}
        className="annotation-panel"
      >
        <AnnotationPage
          key={`${drawing?.id || 'empty'}-${drawing?.page_number || 1}`}
          drawing={drawing}
          mode={mode}
          catalog={catalog}
          documents={availableDocuments}
          onChoose={choose}
          onUpload={onUpload}
          isUploading={isUploading || choosing}
          hidden={hidden}
        />
      </div>
      {pickerOpen && !hidden && (
        <ExistingDrawingPicker
          drawing={drawing}
          onChoose={choose}
          onClose={() => setPickerOpen(false)}
        />
      )}
    </main>
  );
}
