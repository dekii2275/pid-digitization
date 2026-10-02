import { useMemo, useState } from 'react';
import { CheckCircle2, Plus, Save, Scan, Trash2, Type } from 'lucide-react';
import TiledDrawingCanvas from './TiledDrawingCanvas';

const collectionForKind = {
  symbol: 'symbols',
  text: 'texts',
  line: 'lines',
  connection: 'topology_edges',
};

const labels = {
  symbol: 'Symbols',
  text: 'OCR',
  line: 'Lines',
  connection: 'Connections',
};

const cloneScene = (scene) => JSON.parse(JSON.stringify(scene || {
  symbols: [], texts: [], lines: [], topology_edges: [],
}));

const asNumber = (value) => (Number.isFinite(Number(value)) ? Number(value) : 0);

function NumberField({ label, value, onChange }) {
  return <label className="review-field"><span>{label}</span><input type="number" value={asNumber(value)} onChange={(event) => onChange(asNumber(event.target.value))} /></label>;
}

export default function ReviewWorkspace({ drawing, results, jobId, onSave, onZoomChange }) {
  const [scene, setScene] = useState(() => cloneScene(results));
  const [selected, setSelected] = useState(null);
  const [activeKind, setActiveKind] = useState('symbol');
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState(results?.review?.saved_at || null);
  const [saveError, setSaveError] = useState('');
  const [editingItem, setEditingItem] = useState(null);
  const [drawMode, setDrawMode] = useState(null);

  const selectedCollection = collectionForKind[selected?.kind];
  const selectedItem = selectedCollection
    ? scene[selectedCollection]?.find((item) => String(item.id) === String(selected.id))
    : null;

  const setSelection = (item) => {
    if (!item) return;
    setSelected({ kind: item.kind, id: String(item.id) });
    setActiveKind(item.kind);
    if (!editingItem || editingItem.kind !== item.kind || String(editingItem.id) !== String(item.id)) setEditingItem(null);
  };

  const updateItem = (kind, id, patch) => {
    const collection = collectionForKind[kind];
    if (!collection) return;
    setScene((current) => ({
      ...current,
      [collection]: current[collection].map((item) => String(item.id) === String(id) ? { ...item, ...patch } : item),
    }));
    setDirty(true);
  };

  const removeSelected = () => {
    if (!selected || !selectedCollection) return;
    setScene((current) => ({
      ...current,
      [selectedCollection]: current[selectedCollection].filter((item) => String(item.id) !== String(selected.id)),
    }));
    setSelected(null);
    setEditingItem(null);
    setDirty(true);
  };

  const createManualItem = (kind, box) => {
    const id = `manual-${kind}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    const item = kind === 'text'
      ? {
        id,
        text: '',
        confidence: 1,
        source: 'manual',
        ocr_engine: 'Manual',
        x: box.x,
        y: box.y,
        width: box.width,
        height: box.height,
      }
      : {
        id,
        type: 'Manual symbol',
        tag: '',
        confidence: 1,
        source: 'manual',
        x: box.x,
        y: box.y,
        width: box.width,
        height: box.height,
        rotation: 0,
      };
    const collection = collectionForKind[kind];
    const selection = { kind, id };
    setScene((current) => ({ ...current, [collection]: [...(current[collection] || []), item] }));
    setSelected(selection);
    setActiveKind(kind);
    setEditingItem(selection);
    setDrawMode(null);
    setDirty(true);
  };

  const nearbyOcr = useMemo(() => {
    if (selected?.kind !== 'symbol' || !selectedItem) return [];
    const centerX = asNumber(selectedItem.x) + asNumber(selectedItem.width) / 2;
    const centerY = asNumber(selectedItem.y) + asNumber(selectedItem.height) / 2;
    return (scene.texts || [])
      .map((text) => {
        const textX = asNumber(text.x) + asNumber(text.width) / 2;
        const textY = asNumber(text.y) + asNumber(text.height) / 2;
        return { text, distance: Math.hypot(centerX - textX, centerY - textY) };
      })
      .filter(({ distance }) => distance <= Math.max(240, asNumber(selectedItem.width) * 2, asNumber(selectedItem.height) * 2))
      .sort((a, b) => a.distance - b.distance)
      .slice(0, 5);
  }, [scene.texts, selected?.kind, selectedItem]);

  const save = async () => {
    if (!jobId || !onSave || saving) return;
    setSaving(true);
    setSaveError('');
    try {
      const response = await onSave(scene);
      setSavedAt(response.saved_at);
      setDirty(false);
    } catch (error) {
      setSaveError(error.message || 'Không thể lưu kết quả review.');
    } finally {
      setSaving(false);
    }
  };

  if (!drawing || !results) {
    return <main className="review-empty"><h2>Chưa có kết quả để review</h2><p>Upload bản vẽ, chạy pipeline, sau đó mở tab Review để chỉnh sửa và chốt kết quả.</p></main>;
  }

  const collection = scene[collectionForKind[activeKind]] || [];
  const updateSelected = (patch) => selected && updateItem(selected.kind, selected.id, patch);
  const isEditing = Boolean(editingItem && selected && editingItem.kind === selected.kind && String(editingItem.id) === String(selected.id));
  const showDetections = !isEditing;
  const showTags = !isEditing;
  const showConnections = !isEditing || selected?.kind === 'line';

  return <main className="review-workspace">
    <aside className="review-inspector">
      <div className="review-header"><div><strong>AI REVIEW</strong><small>{dirty ? 'Có thay đổi chưa lưu' : savedAt ? 'Đã lưu kết quả cuối cùng' : 'Chưa có thay đổi'}</small></div><button className="review-save" disabled={!dirty || saving || !jobId} onClick={save}><Save size={15} /> {saving ? 'Đang lưu…' : 'Lưu kết quả'}</button></div>
      <div className="review-tabs">{Object.keys(labels).map((kind) => <button key={kind} className={activeKind === kind ? 'active' : ''} onClick={() => setActiveKind(kind)}>{labels[kind]} <span>{scene[collectionForKind[kind]]?.length || 0}</span></button>)}</div>
      <div className="review-list">{collection.map((item, index) => <button key={item.id || index} className={selected?.kind === activeKind && String(selected.id) === String(item.id) ? 'selected' : ''} onClick={() => setSelection({ kind: activeKind, id: item.id })}><b>{activeKind === 'text' ? item.text : activeKind === 'connection' ? `${item.source} → ${item.target}` : item.type || item.id}</b><small>{activeKind === 'symbol' ? `${Math.round(asNumber(item.confidence) * 100)}%` : item.id}</small></button>)}</div>
      <div className="review-manual-tools">
        <div className="review-manual-tools__heading"><div><strong><Plus size={14} /> Thêm thủ công</strong><small>Kéo trên bản vẽ để tạo bounding box còn thiếu</small></div>{drawMode && <button type="button" className="review-draw-cancel" onClick={() => setDrawMode(null)}>Hủy</button>}</div>
        <div className="review-manual-tools__buttons">
          <button type="button" className={drawMode === 'symbol' ? 'active' : ''} onClick={() => setDrawMode((mode) => mode === 'symbol' ? null : 'symbol')}><Scan size={14} /> Symbol / tag</button>
          <button type="button" className={drawMode === 'text' ? 'active' : ''} onClick={() => setDrawMode((mode) => mode === 'text' ? null : 'text')}><Type size={14} /> OCR / text</button>
        </div>
        {drawMode && <p className="review-draw-hint">Đang ở chế độ vẽ {drawMode === 'text' ? 'OCR' : 'symbol/tag'} — kéo từ góc này sang góc đối diện.</p>}
      </div>
      {selectedItem ? <div className="review-properties">
        <div className="review-selection-title"><div><small>{labels[selected.kind]}</small><h2>{selected.kind === 'text' ? selectedItem.text : selected.kind === 'connection' ? `${selectedItem.source} → ${selectedItem.target}` : selectedItem.type || selectedItem.id}</h2></div><button title="Xóa kết quả này" onClick={removeSelected}><Trash2 size={15} /></button></div>
        <button className={`review-edit-toggle ${isEditing ? 'active' : ''}`} onClick={() => setEditingItem(isEditing ? null : selected)}>{isEditing ? 'Hoàn tất chỉnh sửa' : 'Bắt đầu chỉnh sửa'}</button>
        <fieldset className="review-edit-fields" disabled={!isEditing}>
        {selected.kind === 'symbol' && <>
          <label className="review-field review-wide"><span>Ký hiệu / loại</span><input value={selectedItem.type || ''} onChange={(event) => updateSelected({ type: event.target.value })} /></label>
          <label className="review-field review-wide"><span>ID</span><input value={selectedItem.id || ''} onChange={(event) => { const id = event.target.value; updateSelected({ id }); setSelected({ kind: 'symbol', id }); }} /></label>
          <label className="review-field review-wide"><span>Tag / nhãn</span><input value={selectedItem.tag || ''} onChange={(event) => updateSelected({ tag: event.target.value })} placeholder="Ví dụ: P-101A" /></label>
          <div className="review-field-grid"><NumberField label="X" value={selectedItem.x} onChange={(x) => updateSelected({ x })} /><NumberField label="Y" value={selectedItem.y} onChange={(y) => updateSelected({ y })} /><NumberField label="Width" value={selectedItem.width} onChange={(width) => updateSelected({ width: Math.max(4, width) })} /><NumberField label="Height" value={selectedItem.height} onChange={(height) => updateSelected({ height: Math.max(4, height) })} /></div>
          <div className="review-meta"><span>Confidence</span><b>{Math.round(asNumber(selectedItem.confidence) * 100)}%</b></div>
          <div className="nearby-ocr"><strong>OCR xung quanh</strong>{nearbyOcr.length ? nearbyOcr.map(({ text, distance }) => <button key={text.id} onClick={() => setSelection({ kind: 'text', id: text.id })}>{text.text}<small>{Math.round(distance)} px</small></button>) : <p>Không có OCR gần bounding box này.</p>}</div>
        </>}
        {selected.kind === 'text' && <>
          <label className="review-field review-wide"><span>Nội dung OCR</span><input value={selectedItem.text || ''} onChange={(event) => updateSelected({ text: event.target.value })} /></label>
          <div className="review-field-grid"><NumberField label="X" value={selectedItem.x} onChange={(x) => updateSelected({ x })} /><NumberField label="Y" value={selectedItem.y} onChange={(y) => updateSelected({ y })} /><NumberField label="Width" value={selectedItem.width} onChange={(width) => updateSelected({ width: Math.max(4, width) })} /><NumberField label="Height" value={selectedItem.height} onChange={(height) => updateSelected({ height: Math.max(4, height) })} /></div>
          <div className="review-meta"><span>Confidence</span><b>{Math.round(asNumber(selectedItem.confidence) * 100)}%</b></div>
        </>}
        {selected.kind === 'line' && <><div className="review-field-grid"><NumberField label="X1" value={selectedItem.x1} onChange={(x1) => updateSelected({ x1 })} /><NumberField label="Y1" value={selectedItem.y1} onChange={(y1) => updateSelected({ y1 })} /><NumberField label="X2" value={selectedItem.x2} onChange={(x2) => updateSelected({ x2 })} /><NumberField label="Y2" value={selectedItem.y2} onChange={(y2) => updateSelected({ y2 })} /></div><label className="review-field review-wide"><span>Orientation</span><input value={selectedItem.orientation || ''} onChange={(event) => updateSelected({ orientation: event.target.value })} /></label><p className="review-help">Kéo trực tiếp đường trên canvas để dịch cả segment.</p></>}
        {selected.kind === 'connection' && <><label className="review-field review-wide"><span>Source symbol</span><select value={selectedItem.source || ''} onChange={(event) => updateSelected({ source: event.target.value })}>{scene.symbols.map((symbol) => <option key={symbol.id} value={symbol.id}>{symbol.id} · {symbol.type}</option>)}</select></label><label className="review-field review-wide"><span>Target symbol</span><select value={selectedItem.target || ''} onChange={(event) => updateSelected({ target: event.target.value })}>{scene.symbols.map((symbol) => <option key={symbol.id} value={symbol.id}>{symbol.id} · {symbol.type}</option>)}</select></label><label className="review-field review-wide"><span>Flow direction</span><input value={selectedItem.flow_direction || ''} onChange={(event) => updateSelected({ flow_direction: event.target.value })} /></label><p className="review-help">Connection được vẽ từ tâm source đến target; các segment AI vẫn được giữ trong kết quả.</p></>}
        </fieldset>
      </div> : <div className="review-properties review-placeholder">Chọn một mục trên canvas hoặc danh sách để chỉnh sửa.</div>}
      {saveError && <div className="review-save-error">{saveError}</div>}{savedAt && <div className="review-saved"><CheckCircle2 size={14} /> Lưu lúc {new Date(savedAt).toLocaleString()}</div>}
    </aside>
    <section className="review-canvas-pane"><div className="review-canvas-toolbar"><span>{drawMode ? `Đang vẽ ${drawMode === 'text' ? 'OCR' : 'symbol/tag'} — kéo để tạo box` : isEditing ? 'Đang chỉnh sửa object đã chọn' : 'Chọn object để xem thông tin; bấm Bắt đầu chỉnh sửa trước khi thay đổi'}</span><span><i className="legend-symbol" /> Symbol <i className="legend-text" /> OCR <i className="legend-line" /> Line <i className="legend-connect" /> Connect</span></div><TiledDrawingCanvas drawing={drawing} results={scene} showDetections={showDetections} showTags={showTags} showConnections={showConnections} reviewMode selectedItem={selected} onSelectItem={setSelection} onUpdateItem={updateItem} onCreateItem={createManualItem} drawMode={drawMode} onZoomChange={onZoomChange} /></section>
  </main>;
}
