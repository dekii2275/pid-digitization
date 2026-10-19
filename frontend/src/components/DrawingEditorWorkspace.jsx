import { useCallback, useEffect, useRef, useState } from 'react';
import { FolderOpen, RefreshCw } from 'lucide-react';
import ExistingDrawingPicker from './ExistingDrawingPicker';
import ReviewWorkspace from './ReviewWorkspace';
import { getDocumentPage } from '../services/annotations';
import { downloadPageDxf, getPageReviewScene, savePageReviewScene } from '../services/documents';
import './DrawingEditorWorkspace.css';

const sourceNames = {
  review: 'Bản chỉnh sửa đã lưu',
  processed: 'Kết quả AI gần nhất',
  annotations: 'Nhãn đã lưu',
  empty: 'Trang chưa có dữ liệu',
};

export default function DrawingEditorWorkspace({ target, hidden }) {
  const [active, setActive] = useState(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const requestId = useRef(0);
  const consumedTarget = useRef(null);

  const open = useCallback(
    async (id, page = 1, origin = 'latest') => {
      if (saving) return false;
      if (dirty && !window.confirm('Có thay đổi chưa lưu. Bỏ thay đổi để mở dữ liệu khác?'))
        return false;
      const request = ++requestId.current;
      setLoading(true);
      setError('');
      setMessage('');
      try {
        const [drawing, bundle] = await Promise.all([
          getDocumentPage(id, page),
          getPageReviewScene(id, page, origin),
        ]);
        if (request !== requestId.current) return false;
        setActive({ drawing, bundle, serial: request });
        setDirty(false);
        return true;
      } catch (cause) {
        if (request === requestId.current) setError(cause.message);
        return false;
      } finally {
        if (request === requestId.current) setLoading(false);
      }
    },
    [dirty, saving],
  );
  useEffect(() => {
    if (hidden || !target || target === consumedTarget.current) return;
    consumedTarget.current = target;
    open(target.id, target.page_number || 1, target.origin || 'latest');
  }, [target, hidden, open]);
  useEffect(() => {
    if (!dirty) return undefined;
    const warn = (event) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);
  const save = async (scene) => {
    if (loading || saving) throw new Error('Vui lòng đợi thao tác hiện tại hoàn tất.');
    setSaving(true);
    setError('');
    try {
      const response = await savePageReviewScene(active.drawing.id, active.drawing.page_number, {
        version: active.bundle.version,
        generation: active.bundle.generation,
        scene,
      });
      setActive((current) => ({
        ...current,
        bundle: {
          ...current.bundle,
          version: response.version,
          generation: response.generation,
          scene: response.result,
          origin: 'review',
          saved_at: response.saved_at,
          available_sources: [...new Set(['review', ...current.bundle.available_sources])],
        },
      }));
      setMessage(`Đã lưu bản chỉnh sửa v${response.version}.`);
      return response;
    } finally {
      setSaving(false);
    }
  };
  const exportDxf = async () => {
    setError('');
    setMessage('');
    try {
      await downloadPageDxf(
        active.drawing.id,
        active.drawing.page_number,
        active.bundle.version,
        active.drawing.name,
      );
      setMessage('Đã xuất DXF: symbol/block, tag, text và đường ống có thể chỉnh sửa trong CAD.');
    } catch (cause) {
      setError(cause.message);
    }
  };
  return (
    <section className="drawing-editor-workspace" hidden={hidden}>
      <header className="drawing-editor-toolbar">
        <button onClick={() => setPickerOpen(true)} disabled={loading || saving}>
          <FolderOpen size={15} /> Mở bản vẽ đã xử lý
        </button>
        {active && (
          <>
            <strong title={active.drawing.name}>{active.drawing.name}</strong>
            <select
              aria-label="Trang chỉnh sửa"
              value={active.drawing.page_number}
              disabled={loading || saving}
              onChange={(event) => open(active.drawing.id, Number(event.target.value))}
            >
              {Array.from({ length: active.drawing.page_count }, (_, index) => (
                <option key={index + 1} value={index + 1}>
                  Trang {index + 1}
                </option>
              ))}
            </select>
            <select
              aria-label="Nguồn bản vẽ"
              value={active.bundle.origin}
              disabled={loading || saving}
              onChange={(event) =>
                open(active.drawing.id, active.drawing.page_number, event.target.value)
              }
            >
              {[...new Set([active.bundle.origin, ...active.bundle.available_sources])].map(
                (source) => (
                  <option key={source} value={source}>
                    {sourceNames[source]}
                  </option>
                ),
              )}
            </select>
            <button
              onClick={() => open(active.drawing.id, active.drawing.page_number)}
              disabled={loading || saving}
            >
              <RefreshCw size={14} /> Tải lại bản đã lưu
            </button>
            <span>
              {active.bundle.version
                ? `Bản lưu v${active.bundle.version}`
                : 'Chưa lưu bản chỉnh sửa'}
            </span>
          </>
        )}
      </header>
      {error && (
        <p className="drawing-editor-notice is-error" role="alert">
          {error}
        </p>
      )}
      {message && (
        <p className="drawing-editor-notice" role="status">
          {message}
        </p>
      )}
      {loading && (
        <p className="drawing-editor-notice" role="status">
          Đang mở bản vẽ và kết quả đã lưu…
        </p>
      )}
      {active ? (
        <div className={`drawing-editor-body ${loading ? 'is-loading' : ''}`} aria-busy={loading}>
          <ReviewWorkspace
            key={active.serial}
            drawing={active.drawing}
            results={active.bundle.scene}
            onSave={save}
            onDirtyChange={setDirty}
            onExportDxf={exportDxf}
            canExport={active.bundle.origin === 'review' && active.bundle.version > 0}
            readOnly={loading}
          />
        </div>
      ) : (
        <div className="review-empty">
          <h2>Chỉnh sửa bản vẽ sau xử lý</h2>
          <p>Mở bản vẽ từ thư viện để tiếp tục sửa kết quả AI hoặc nhãn đã lưu theo từng trang.</p>
        </div>
      )}
      {pickerOpen && (
        <ExistingDrawingPicker
          drawing={active?.drawing}
          onChoose={open}
          onClose={() => setPickerOpen(false)}
        />
      )}
    </section>
  );
}
