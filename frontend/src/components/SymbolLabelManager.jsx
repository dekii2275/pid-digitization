import { useEffect, useMemo, useState } from 'react';
import { ImageUp, ListFilter, Pencil, RotateCcw, Save, Search, X } from 'lucide-react';
import { symbolLabelCount, symbolLabels } from '../data/symbolLabels';

const storageKey = 'vpi-symbol-label-statuses';
const editsStorageKey = 'vpi-symbol-label-edits';

function readStatuses() {
  try {
    const stored = JSON.parse(window.localStorage.getItem(storageKey) || '{}');
    return Object.fromEntries(symbolLabels.map(({ id }) => [id, stored[id] ?? true]));
  } catch {
    return Object.fromEntries(symbolLabels.map(({ id }) => [id, true]));
  }
}

function readEdits() {
  try {
    const stored = JSON.parse(window.localStorage.getItem(editsStorageKey) || '{}');
    return Object.fromEntries(Object.entries(stored).filter(([, value]) => (
      value && typeof value === 'object' && (typeof value.name === 'string' || typeof value.preview === 'string')
    )));
  } catch {
    return {};
  }
}

export default function SymbolLabelManager() {
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('All');
  const [statuses, setStatuses] = useState(readStatuses);
  const [edits, setEdits] = useState(readEdits);
  const [editingId, setEditingId] = useState(null);
  const [draft, setDraft] = useState(null);
  const [uploadError, setUploadError] = useState('');
  const categories = useMemo(() => ['All', ...new Set(symbolLabels.map((item) => item.category))], []);
  const labels = useMemo(() => symbolLabels.map((item) => ({ ...item, ...edits[item.id] })), [edits]);
  const visibleLabels = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return labels.filter((item) => (
      (category === 'All' || item.category === category)
      && (!normalizedQuery || `${item.id} ${item.name}`.toLowerCase().includes(normalizedQuery))
    ));
  }, [category, labels, query]);
  const enabledCount = Object.values(statuses).filter(Boolean).length;
  const editingOriginal = editingId ? symbolLabels.find((item) => item.id === editingId) : null;

  useEffect(() => {
    window.localStorage.setItem(storageKey, JSON.stringify(statuses));
  }, [statuses]);

  useEffect(() => {
    window.localStorage.setItem(editsStorageKey, JSON.stringify(edits));
  }, [edits]);

  const setAllVisible = (enabled) => {
    setStatuses((current) => ({
      ...current,
      ...Object.fromEntries(visibleLabels.map(({ id }) => [id, enabled])),
    }));
  };

  const openEditor = (item) => {
    setEditingId(item.id);
    setDraft({ name: item.name, preview: item.preview });
    setUploadError('');
  };

  const closeEditor = () => {
    setEditingId(null);
    setDraft(null);
    setUploadError('');
  };

  const uploadPreview = (file) => {
    if (!file) return;
    if (!file.type.startsWith('image/')) {
      setUploadError('Vui lòng chọn tệp ảnh (PNG, JPG, WEBP hoặc SVG).');
      return;
    }
    if (file.size > 2 * 1024 * 1024) {
      setUploadError('Ảnh tối đa 2 MB để có thể lưu trên trình duyệt.');
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      setDraft((current) => ({ ...current, preview: String(reader.result) }));
      setUploadError('');
    };
    reader.onerror = () => setUploadError('Không thể đọc tệp ảnh này.');
    reader.readAsDataURL(file);
  };

  const saveEdit = () => {
    const nextName = draft?.name?.trim();
    if (!editingOriginal || !nextName) {
      setUploadError('Tên nhãn không được để trống.');
      return;
    }
    setEdits((current) => ({
      ...current,
      [editingOriginal.id]: { name: nextName, preview: draft.preview },
    }));
    closeEditor();
  };

  const resetEdit = () => {
    if (!editingOriginal) return;
    setEdits((current) => {
      const next = { ...current };
      delete next[editingOriginal.id];
      return next;
    });
    closeEditor();
  };

  return <main className="symbol-label-manager">
    <section className="label-manager-header">
      <div>
        <p>THƯ VIỆN NHÃN SYMBOL</p>
        <h2>Quản lý nhãn symbol</h2>
        <span>Đã nhập {symbolLabelCount} nhãn từ 3 bản vẽ symbology trong thư mục <code>label_symbol</code>.</span>
      </div>
      <div className="label-manager-summary"><b>{enabledCount}</b><span>/ {symbolLabelCount} đang bật</span></div>
    </section>
    <section className="label-manager-controls" aria-label="Lọc nhãn symbol">
      <label className="label-search"><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Tìm symbol hoặc tên" /></label>
      <label className="label-filter"><ListFilter size={15} /><select value={category} onChange={(event) => setCategory(event.target.value)}>{categories.map((item) => <option key={item}>{item}</option>)}</select></label>
      <button type="button" onClick={() => setAllVisible(true)}>Bật tất cả đang xem</button>
      <button type="button" className="label-manager-off" onClick={() => setAllVisible(false)}>Tắt tất cả đang xem</button>
    </section>
    <section className="label-table-wrap">
      <table className="symbol-label-table">
        <thead><tr><th>Symbol</th><th>Tên của nó</th><th>Trạng thái</th></tr></thead>
        <tbody>
          {visibleLabels.map((item) => {
            const isEnabled = statuses[item.id];
            return <tr key={item.id} className={isEnabled ? '' : 'is-disabled'} title={`${item.category} · ${item.source}`}>
              <td><div className="symbol-cell"><img className="symbol-preview" src={item.preview} alt={`Ký hiệu ${item.name}`} /><code>{item.id}</code></div></td>
              <td><div className="symbol-name"><strong>{item.name}</strong><small>{item.category}</small><button type="button" className="edit-label-button" onClick={() => openEditor(item)}><Pencil size={12} /> Chỉnh sửa</button></div></td>
              <td><button type="button" className={`status-toggle ${isEnabled ? 'is-on' : ''}`} aria-pressed={isEnabled} onClick={() => setStatuses((current) => ({ ...current, [item.id]: !current[item.id] }))}><i /><span>{isEnabled ? 'Bật' : 'Tắt'}</span></button></td>
            </tr>;
          })}
          {visibleLabels.length === 0 && <tr><td className="label-empty" colSpan="3">Không tìm thấy nhãn phù hợp.</td></tr>}
        </tbody>
      </table>
    </section>
    {editingOriginal && draft && <div className="label-editor-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) closeEditor(); }}>
      <section className="label-editor-dialog" role="dialog" aria-modal="true" aria-labelledby="label-editor-title">
        <header><div><small>CHỈNH SỬA NHÃN</small><h3 id="label-editor-title">{editingOriginal.id}</h3></div><button type="button" className="label-editor-close" onClick={closeEditor} aria-label="Đóng"><X size={18} /></button></header>
        <div className="label-editor-body">
          <div className="label-editor-preview"><img src={draft.preview} alt={`Xem trước ${draft.name}`} /></div>
          <label className="label-editor-field">Tên nhãn<input value={draft.name} onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))} autoFocus /></label>
          <label className="label-image-upload"><ImageUp size={17} /><span>Tải ảnh nhãn mới</span><small>PNG, JPG, WEBP hoặc SVG - tối đa 2 MB</small><input type="file" accept="image/png,image/jpeg,image/webp,image/svg+xml" onChange={(event) => { uploadPreview(event.target.files?.[0]); event.target.value = ''; }} /></label>
          {uploadError && <p className="label-editor-error">{uploadError}</p>}
        </div>
        <footer><button type="button" className="label-editor-reset" onClick={resetEdit}><RotateCcw size={14} /> Khôi phục gốc</button><span /><button type="button" className="label-editor-cancel" onClick={closeEditor}>Hủy</button><button type="button" className="label-editor-save" onClick={saveEdit}><Save size={14} /> Lưu thay đổi</button></footer>
      </section>
    </div>}
  </main>;
}
