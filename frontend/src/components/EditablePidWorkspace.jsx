import { useMemo, useRef, useState } from 'react';
import { Download, FileJson, Maximize2, Plus, Save, Search, Trash2, ZoomIn, ZoomOut } from 'lucide-react';
import { symbolLabels } from '../data/symbolLabels';

const statusStorageKey = 'vpi-symbol-label-statuses';
const editsStorageKey = 'vpi-symbol-label-edits';
const MIN_VIEW_SIZE = 160;

const clamp = (value, minimum, maximum) => Math.min(Math.max(value, minimum), maximum);

const readStorage = (key, fallback) => {
  try {
    return JSON.parse(window.localStorage.getItem(key) || JSON.stringify(fallback));
  } catch {
    return fallback;
  }
};

const cloneScene = (scene, drawing) => {
  const source = scene?.source || {};
  return JSON.parse(JSON.stringify({
    ...scene,
    source: {
      ...source,
      width: Number(source.width || drawing?.width || 1),
      height: Number(source.height || drawing?.height || 1),
    },
    symbols: Array.isArray(scene?.symbols) ? scene.symbols : [],
    texts: Array.isArray(scene?.texts) ? scene.texts : [],
    lines: Array.isArray(scene?.lines) ? scene.lines : [],
    topology_edges: Array.isArray(scene?.topology_edges) ? scene.topology_edges : [],
  }));
};

const sourceOf = (scene) => ({
  width: Math.max(1, Number(scene?.source?.width) || 1),
  height: Math.max(1, Number(scene?.source?.height) || 1),
});

const labelForSymbol = (symbol) => symbol?.tag || symbol?.id || symbol?.type || 'Symbol';

const safeFileName = (name) => String(name || 'pid-drawing').replace(/[^a-z0-9._-]+/gi, '_').replace(/^_+|_+$/g, '') || 'pid-drawing';

const escapeXml = (value) => String(value ?? '')
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;')
  .replace(/'/g, '&apos;');

const number = (value, fallback = 0) => Number.isFinite(Number(value)) ? Number(value) : fallback;

const symbolGeometry = (symbol) => {
  const width = Math.max(12, number(symbol.width, 60));
  const height = Math.max(12, number(symbol.height, 42));
  const lower = `${symbol.type || ''} ${symbol.category || ''}`.toLowerCase();
  return { width, height, lower };
};

function VectorSymbol({ symbol, selected, onPointerDown, onClick }) {
  const { width, height, lower } = symbolGeometry(symbol);
  const stroke = selected ? '#d97706' : '#174b62';
  const fill = selected ? '#fff7df' : '#f8fbfd';
  const common = { fill, stroke, strokeWidth: selected ? 3 : 2, vectorEffect: 'non-scaling-stroke' };
  let shape;
  if (lower.includes('valve') || lower.includes('blind')) {
    shape = <><path d={`M 4 ${height / 2} L ${width * .42} 4 L ${width * .42} ${height - 4} Z M ${width - 4} ${height / 2} L ${width * .58} 4 L ${width * .58} ${height - 4} Z`} {...common} /><line x1={width / 2} y1="4" x2={width / 2} y2={height - 4} stroke={stroke} strokeWidth="2" vectorEffect="non-scaling-stroke" /></>;
  } else if (lower.includes('pump') || lower.includes('compressor') || lower.includes('blower')) {
    shape = <><circle cx={width / 2} cy={height / 2} r={Math.min(width, height) * .34} {...common} /><path d={`M ${width * .30} ${height * .50} L ${width * .72} ${height * .50} M ${width * .60} ${height * .38} L ${width * .74} ${height * .50} L ${width * .60} ${height * .62}`} fill="none" stroke={stroke} strokeWidth="2" vectorEffect="non-scaling-stroke" /></>;
  } else if (lower.includes('instrument') || lower.includes('indicator') || lower.includes('gauge') || lower.includes('transmitter')) {
    shape = <><circle cx={width / 2} cy={height / 2} r={Math.min(width, height) * .34} {...common} /><line x1={width / 2} y1="0" x2={width / 2} y2={height * .16} stroke={stroke} strokeWidth="2" vectorEffect="non-scaling-stroke" /></>;
  } else if (lower.includes('tank') || lower.includes('drum') || lower.includes('column') || lower.includes('separator') || lower.includes('heater') || lower.includes('exchanger')) {
    shape = <><rect x="3" y="3" width={width - 6} height={height - 6} rx={Math.min(width, height) * .12} {...common} /><line x1="3" y1={height * .25} x2={width - 3} y2={height * .25} stroke={stroke} strokeWidth="1.5" vectorEffect="non-scaling-stroke" /><line x1="3" y1={height * .75} x2={width - 3} y2={height * .75} stroke={stroke} strokeWidth="1.5" vectorEffect="non-scaling-stroke" /></>;
  } else if (lower.includes('line') || lower.includes('piping') || lower.includes('arrow')) {
    shape = <><line x1="3" y1={height / 2} x2={width - 10} y2={height / 2} stroke={stroke} strokeWidth="3" vectorEffect="non-scaling-stroke" /><path d={`M ${width - 10} ${height / 2} L ${width - 20} ${height * .28} L ${width - 20} ${height * .72} Z`} fill={stroke} /></>;
  } else {
    shape = <><rect x="3" y="3" width={width - 6} height={height - 6} rx="4" {...common} /><circle cx={width / 2} cy={height / 2} r={Math.min(width, height) * .2} fill="none" stroke={stroke} strokeWidth="2" vectorEffect="non-scaling-stroke" /></>;
  }

  return <g transform={`translate(${number(symbol.x)} ${number(symbol.y)})`} className={`pid-editor-symbol ${selected ? 'is-selected' : ''}`} onPointerDown={onPointerDown} onClick={onClick}>
    <rect x="0" y="0" width={width} height={height} fill="transparent" stroke="transparent" />
    {shape}
    <text x={width / 2} y={height + Math.max(16, height * .24)} textAnchor="middle" className="pid-editor-symbol-label">{labelForSymbol(symbol)}</text>
  </g>;
}

function linePoints(line) {
  if (Array.isArray(line?.start) && Array.isArray(line?.end)) return [line.start, line.end];
  if (Array.isArray(line?.points)) return line.points;
  if ([line?.x1, line?.y1, line?.x2, line?.y2].every((value) => Number.isFinite(Number(value)))) return [[line.x1, line.y1], [line.x2, line.y2]];
  return [];
}

function renderLineMarkup(line) {
  const points = linePoints(line);
  return points.length > 1 ? points.map((point) => `${number(point[0])},${number(point[1])}`).join(' ') : '';
}

function symbolMarkup(symbol) {
  const { width, height, lower } = symbolGeometry(symbol);
  const x = number(symbol.x);
  const y = number(symbol.y);
  const stroke = '#174b62';
  const label = escapeXml(labelForSymbol(symbol));
  let shape = `<rect x="3" y="3" width="${width - 6}" height="${height - 6}" rx="4" fill="#f8fbfd" stroke="${stroke}" stroke-width="2"/>`;
  if (lower.includes('valve') || lower.includes('blind')) shape = `<path d="M 4 ${height / 2} L ${width * .42} 4 L ${width * .42} ${height - 4} Z M ${width - 4} ${height / 2} L ${width * .58} 4 L ${width * .58} ${height - 4} Z" fill="#f8fbfd" stroke="${stroke}" stroke-width="2"/><line x1="${width / 2}" y1="4" x2="${width / 2}" y2="${height - 4}" stroke="${stroke}" stroke-width="2"/>`;
  else if (lower.includes('pump') || lower.includes('compressor') || lower.includes('blower')) shape = `<circle cx="${width / 2}" cy="${height / 2}" r="${Math.min(width, height) * .34}" fill="#f8fbfd" stroke="${stroke}" stroke-width="2"/><path d="M ${width * .30} ${height * .50} L ${width * .72} ${height * .50} M ${width * .60} ${height * .38} L ${width * .74} ${height * .50} L ${width * .60} ${height * .62}" fill="none" stroke="${stroke}" stroke-width="2"/>`;
  else if (lower.includes('instrument') || lower.includes('indicator') || lower.includes('gauge') || lower.includes('transmitter')) shape = `<circle cx="${width / 2}" cy="${height / 2}" r="${Math.min(width, height) * .34}" fill="#f8fbfd" stroke="${stroke}" stroke-width="2"/><line x1="${width / 2}" y1="0" x2="${width / 2}" y2="${height * .16}" stroke="${stroke}" stroke-width="2"/>`;
  return `<g transform="translate(${x} ${y})"><g>${shape}</g><text x="${width / 2}" y="${height + Math.max(16, height * .24)}" text-anchor="middle" font-family="Arial, sans-serif" font-size="${Math.max(12, Math.min(24, height * .24))}" fill="#174b62">${label}</text></g>`;
}

function sceneToDexpi(scene, drawing) {
  const source = sourceOf(scene);
  const name = escapeXml(drawing?.name || scene?.source?.name || 'P&ID drawing');
  const symbols = (scene.symbols || []).map((symbol, index) => {
    const tag = escapeXml(symbol.tag || symbol.id || `sym-${index + 1}`);
    const type = escapeXml(symbol.type || symbol.category || 'Equipment');
    const element = `${symbol.category || ''} ${symbol.type || ''}`.toLowerCase().includes('pump') ? 'Pump'
      : `${symbol.category || ''} ${symbol.type || ''}`.toLowerCase().includes('valve') ? 'Valve'
        : `${symbol.category || ''} ${symbol.type || ''}`.toLowerCase().includes('instrument') ? 'Instrument' : 'Equipment';
    return `  <${element} id="${tag}" type="${type}" x="${number(symbol.x)}" y="${number(symbol.y)}" width="${number(symbol.width)}" height="${number(symbol.height)}" source="${escapeXml(symbol.source || 'AI')}"/>`;
  }).join('\n');
  const lines = (scene.lines || []).map((line, index) => `  <PipeLine id="${escapeXml(line.id || `line-${index + 1}`)}" points="${escapeXml(renderLineMarkup(line))}" orientation="${escapeXml(line.orientation || '')}"/>`).join('\n');
  const texts = (scene.texts || []).map((text, index) => `  <Text id="${escapeXml(text.id || `text-${index + 1}`)}" value="${escapeXml(text.text)}" x="${number(text.x)}" y="${number(text.y)}" width="${number(text.width)}" height="${number(text.height)}"/>`).join('\n');
  const edges = (scene.topology_edges || []).map((edge, index) => `  <Connection id="${escapeXml(edge.id || `connection-${index + 1}`)}" from="${escapeXml(edge.source)}" to="${escapeXml(edge.target)}" flowDirection="${escapeXml(edge.flow_direction || '')}"/>`).join('\n');
  return `<?xml version="1.0" encoding="UTF-8"?>
<PipingAndInstrumentationDiagram xmlns:dexpi="http://sandbox.dexpi.org/rdl" drawingName="${name}" width="${source.width}" height="${source.height}" schemaVersion="0.1">
${symbols}${symbols && (lines || texts || edges) ? '\n' : ''}${lines}${lines && (texts || edges) ? '\n' : ''}${texts}${texts && edges ? '\n' : ''}${edges}
</PipingAndInstrumentationDiagram>
`;
}

function sceneToSvg(scene, drawing) {
  const source = sourceOf(scene);
  const lines = (scene.lines || []).map((line) => {
    const points = escapeXml(renderLineMarkup(line));
    return points ? `<polyline points="${points}" fill="none" stroke="#2582a8" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>` : '';
  }).join('');
  const texts = (scene.texts || []).map((text) => `<text x="${number(text.x)}" y="${number(text.y) + Math.max(number(text.height), 16)}" font-family="Arial, sans-serif" font-size="${Math.max(12, Math.min(24, number(text.height) || 14))}" fill="#0f8a55">${escapeXml(text.text)}</text>`).join('');
  const symbols = (scene.symbols || []).map(symbolMarkup).join('');
  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" xmlns:dexpi="http://sandbox.dexpi.org/rdl" width="${source.width}" height="${source.height}" viewBox="0 0 ${source.width} ${source.height}" data-drawing="${escapeXml(drawing?.name || '')}">
  <rect width="100%" height="100%" fill="#ffffff"/>
  <g id="lines">${lines}</g>
  <g id="symbols">${symbols}</g>
  <g id="ocr">${texts}</g>
</svg>
`;
}

function downloadText(name, content, type) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 500);
}

// eslint-disable-next-line react-refresh/only-export-components
export function downloadSceneFile(scene, drawing, format) {
  const base = safeFileName(drawing?.name || scene?.source?.name);
  if (format === 'dexpi') downloadText(`${base}.dexpi.xml`, sceneToDexpi(scene, drawing), 'application/xml');
  if (format === 'svg') downloadText(`${base}.svg`, sceneToSvg(scene, drawing), 'image/svg+xml');
  if (format === 'json') downloadText(`${base}.scene.json`, JSON.stringify(scene, null, 2), 'application/json');
}

export default function EditablePidWorkspace({ drawing, results, jobId, onSave, onNotify }) {
  const [scene, setScene] = useState(() => cloneScene(results, drawing));
  const [selectedId, setSelectedId] = useState(null);
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('All');
  const [viewport, setViewport] = useState(() => {
    const source = sourceOf(cloneScene(results, drawing));
    return { x: 0, y: 0, width: source.width, height: source.height };
  });
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState(results?.review?.saved_at || null);
  const svgRef = useRef(null);
  const interactionRef = useRef(null);
  const idCounterRef = useRef(0);
  const source = sourceOf(scene);
  const edits = readStorage(editsStorageKey, {});
  const statuses = readStorage(statusStorageKey, {});
  const library = useMemo(() => symbolLabels
    .filter((item) => statuses[item.id] !== false)
    .map((item) => ({ ...item, ...edits[item.id] }))
    .filter((item) => {
      const normalized = query.trim().toLowerCase();
      return (category === 'All' || item.category === category) && (!normalized || `${item.id} ${item.name}`.toLowerCase().includes(normalized));
    }), [category, edits, query, statuses]);
  const categories = useMemo(() => ['All', ...new Set(symbolLabels.map((item) => item.category))], []);
  const selectedSymbol = scene.symbols.find((symbol) => String(symbol.id) === String(selectedId));
  const backgroundUrl = drawing?.preview_url || '';

  const clampViewport = (next) => ({
    ...next,
    width: clamp(next.width, MIN_VIEW_SIZE, source.width),
    height: clamp(next.height, MIN_VIEW_SIZE, source.height),
    x: clamp(next.x, 0, Math.max(0, source.width - next.width)),
    y: clamp(next.y, 0, Math.max(0, source.height - next.height)),
  });

  const pointFromEvent = (event) => {
    const svg = svgRef.current;
    if (!svg) return { x: viewport.x + viewport.width / 2, y: viewport.y + viewport.height / 2 };
    const point = svg.createSVGPoint();
    point.x = event.clientX;
    point.y = event.clientY;
    const transformed = point.matrixTransform(svg.getScreenCTM().inverse());
    return { x: transformed.x, y: transformed.y };
  };

  const updateSymbol = (id, patch) => {
    setScene((current) => ({ ...current, symbols: current.symbols.map((symbol) => String(symbol.id) === String(id) ? { ...symbol, ...patch } : symbol) }));
    setDirty(true);
  };

  const addSymbol = (label) => {
    const size = Math.max(36, Math.min(source.width, source.height) * .035);
    idCounterRef.current += 1;
    const id = `manual-${label.id.toLowerCase()}-${idCounterRef.current}`;
    const x = clamp(viewport.x + viewport.width / 2 - size / 2, 0, Math.max(0, source.width - size));
    const y = clamp(viewport.y + viewport.height / 2 - size * .35, 0, Math.max(0, source.height - size * .7));
    const item = { id, label_id: label.id, type: label.name, category: label.category, tag: '', confidence: 1, source: 'manual', x, y, width: size, height: size * .7, rotation: 0 };
    setScene((current) => ({ ...current, symbols: [...current.symbols, item] }));
    setSelectedId(id);
    setDirty(true);
    onNotify?.(`Đã thêm ${label.id} vào bản vẽ.`);
  };

  const removeSelected = () => {
    if (!selectedSymbol) return;
    setScene((current) => ({
      ...current,
      symbols: current.symbols.filter((symbol) => String(symbol.id) !== String(selectedId)),
      topology_edges: current.topology_edges.filter((edge) => String(edge.source) !== String(selectedId) && String(edge.target) !== String(selectedId)),
    }));
    setSelectedId(null);
    setDirty(true);
  };

  const save = async () => {
    if (!jobId || !onSave || saving) return;
    setSaving(true);
    try {
      const response = await onSave(scene);
      setScene(cloneScene(response.result, drawing));
      setSavedAt(response.saved_at);
      setDirty(false);
      onNotify?.('Đã lưu bản vẽ chỉnh sửa.');
    } catch (error) {
      onNotify?.(error.message || 'Không thể lưu bản vẽ chỉnh sửa.');
    } finally {
      setSaving(false);
    }
  };

  const exportFile = (format) => {
    downloadSceneFile(scene, drawing, format);
    onNotify?.(`Đã xuất file ${format === 'dexpi' ? 'DEXPI XML' : format.toUpperCase()}.`);
  };

  const zoom = (factor) => {
    const nextWidth = clamp(viewport.width / factor, MIN_VIEW_SIZE, source.width);
    const nextHeight = clamp(viewport.height / factor, MIN_VIEW_SIZE, source.height);
    setViewport(clampViewport({ x: viewport.x + (viewport.width - nextWidth) / 2, y: viewport.y + (viewport.height - nextHeight) / 2, width: nextWidth, height: nextHeight }));
  };

  const onPointerDown = (event) => {
    if (event.button !== 0) return;
    const point = pointFromEvent(event);
    interactionRef.current = { type: 'pan', pointerId: event.pointerId, clientX: event.clientX, clientY: event.clientY, viewport, point };
    svgRef.current?.setPointerCapture(event.pointerId);
  };

  const onSymbolPointerDown = (event, symbol) => {
    event.preventDefault();
    event.stopPropagation();
    const point = pointFromEvent(event);
    interactionRef.current = { type: 'symbol', pointerId: event.pointerId, id: symbol.id, point, original: { x: number(symbol.x), y: number(symbol.y) } };
    svgRef.current?.setPointerCapture(event.pointerId);
    setSelectedId(symbol.id);
  };

  const onPointerMove = (event) => {
    const interaction = interactionRef.current;
    if (!interaction || interaction.pointerId !== event.pointerId) return;
    const point = pointFromEvent(event);
    if (interaction.type === 'symbol') {
      const symbol = scene.symbols.find((item) => String(item.id) === String(interaction.id));
      if (!symbol) return;
      updateSymbol(interaction.id, {
        x: clamp(interaction.original.x + point.x - interaction.point.x, 0, Math.max(0, source.width - number(symbol.width))),
        y: clamp(interaction.original.y + point.y - interaction.point.y, 0, Math.max(0, source.height - number(symbol.height))),
      });
    } else {
      const rect = svgRef.current?.getBoundingClientRect();
      if (!rect) return;
      const scaleX = viewport.width / rect.width;
      const scaleY = viewport.height / rect.height;
      setViewport(clampViewport({ ...interaction.viewport, x: interaction.viewport.x - (event.clientX - interaction.clientX) * scaleX, y: interaction.viewport.y - (event.clientY - interaction.clientY) * scaleY }));
    }
  };

  const finishInteraction = () => { interactionRef.current = null; };

  return <main className="pid-editor-workspace">
    <aside className="pid-editor-sidebar">
      <div className="pid-editor-header"><div><strong>P&amp;ID EDITOR</strong><small>{dirty ? 'Có thay đổi chưa lưu' : savedAt ? 'Đã lưu bản chỉnh sửa' : 'Scene từ kết quả AI'}</small></div><button className="review-save" disabled={!dirty || saving || !jobId} onClick={save}><Save size={14} /> {saving ? 'Đang lưu…' : 'Lưu scene'}</button></div>
      <section className="pid-editor-library">
        <div className="pid-editor-section-title"><div><b>Thư viện symbol</b><small>Chọn symbol để thêm vào bản vẽ</small></div><span>{library.length}</span></div>
        <label className="pid-editor-search"><Search size={14} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Tìm ID hoặc tên symbol" /></label>
        <select className="pid-editor-category" value={category} onChange={(event) => setCategory(event.target.value)}>{categories.map((item) => <option key={item}>{item}</option>)}</select>
        <div className="pid-editor-library-list">{library.map((item) => <button type="button" key={item.id} onClick={() => addSymbol(item)}><img src={item.preview} alt="" /><span><b>{item.id}</b><small>{item.name}</small></span><Plus size={14} /></button>)}</div>
      </section>
      {selectedSymbol ? <section className="pid-editor-properties">
        <div className="pid-editor-section-title"><div><b>Symbol đang chọn</b><small>{selectedSymbol.source === 'manual' ? 'Thêm thủ công' : 'AI detected'}</small></div><button type="button" className="pid-editor-delete" title="Xóa symbol" onClick={removeSelected}><Trash2 size={14} /></button></div>
        <label className="review-field review-wide"><span>Loại symbol</span><input value={selectedSymbol.type || ''} onChange={(event) => updateSymbol(selectedSymbol.id, { type: event.target.value })} /></label>
        <label className="review-field review-wide"><span>Tag / ID hiển thị</span><input value={selectedSymbol.tag || ''} onChange={(event) => updateSymbol(selectedSymbol.id, { tag: event.target.value })} placeholder={selectedSymbol.id} /></label>
        <div className="review-field-grid"><label className="review-field"><span>X</span><input type="number" value={number(selectedSymbol.x)} onChange={(event) => updateSymbol(selectedSymbol.id, { x: number(event.target.value) })} /></label><label className="review-field"><span>Y</span><input type="number" value={number(selectedSymbol.y)} onChange={(event) => updateSymbol(selectedSymbol.id, { y: number(event.target.value) })} /></label><label className="review-field"><span>Width</span><input type="number" value={number(selectedSymbol.width)} onChange={(event) => updateSymbol(selectedSymbol.id, { width: Math.max(12, number(event.target.value)) })} /></label><label className="review-field"><span>Height</span><input type="number" value={number(selectedSymbol.height)} onChange={(event) => updateSymbol(selectedSymbol.id, { height: Math.max(12, number(event.target.value)) })} /></label></div>
      </section> : <div className="pid-editor-empty-selection">Chọn symbol trên bản vẽ để chỉnh sửa vị trí, kích thước hoặc xóa.</div>}
      <section className="pid-editor-export"><b>Xuất bản vẽ</b><small>Xuất scene sau khi đã chỉnh sửa xong.</small><div><button type="button" onClick={() => exportFile('dexpi')}><Download size={13} /> DEXPI XML</button><button type="button" onClick={() => exportFile('svg')}><Download size={13} /> SVG kỹ thuật</button><button type="button" onClick={() => exportFile('json')}><FileJson size={13} /> Scene JSON</button></div></section>
    </aside>
    <section className="pid-editor-canvas-pane"><div className="pid-editor-toolbar"><span><b>{drawing?.name || scene.source?.name || 'P&ID'}</b> · {scene.symbols.length} symbols · {scene.lines.length} lines</span><div><button type="button" onClick={() => setViewport({ x: 0, y: 0, width: source.width, height: source.height })} title="Fit drawing"><Maximize2 size={14} /> Fit</button><button type="button" onClick={() => zoom(1.2)} title="Zoom out"><ZoomOut size={14} /></button><button type="button" onClick={() => zoom(0.8)} title="Zoom in"><ZoomIn size={14} /></button></div></div><div className="pid-editor-canvas-wrap"><svg ref={svgRef} viewBox={`${viewport.x} ${viewport.y} ${viewport.width} ${viewport.height}`} preserveAspectRatio="xMidYMid meet" onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={finishInteraction} onPointerCancel={finishInteraction} onWheel={(event) => { event.preventDefault(); zoom(event.deltaY < 0 ? 1.16 : .86); }} aria-label="Bản vẽ P&ID dạng vector có thể chỉnh sửa">
      <rect x="0" y="0" width={source.width} height={source.height} fill="#ffffff" />
      {backgroundUrl && <image href={backgroundUrl} x="0" y="0" width={source.width} height={source.height} preserveAspectRatio="none" opacity=".22" pointerEvents="none" />}
      <g className="pid-editor-lines">{scene.lines.map((line, index) => { const points = renderLineMarkup(line); return points ? <polyline key={line.id || index} points={points} /> : null; })}</g>
      <g className="pid-editor-topology">{scene.topology_edges.map((edge, index) => { const sourceSymbol = scene.symbols.find((item) => String(item.id) === String(edge.source)); const targetSymbol = scene.symbols.find((item) => String(item.id) === String(edge.target)); if (!sourceSymbol || !targetSymbol) return null; return <line key={edge.id || index} x1={number(sourceSymbol.x) + number(sourceSymbol.width) / 2} y1={number(sourceSymbol.y) + number(sourceSymbol.height) / 2} x2={number(targetSymbol.x) + number(targetSymbol.width) / 2} y2={number(targetSymbol.y) + number(targetSymbol.height) / 2} />; })}</g>
      <g className="pid-editor-ocr">{scene.texts.map((text, index) => <g key={text.id || index}><rect x={number(text.x)} y={number(text.y)} width={Math.max(8, number(text.width))} height={Math.max(8, number(text.height))} /><text x={number(text.x)} y={number(text.y) + Math.max(14, number(text.height))}>{text.text}</text></g>)}</g>
      <g className="pid-editor-symbols">{scene.symbols.map((symbol, index) => <VectorSymbol key={symbol.id || index} symbol={symbol} selected={String(selectedId) === String(symbol.id)} onPointerDown={(event) => onSymbolPointerDown(event, symbol)} onClick={(event) => { event.stopPropagation(); setSelectedId(symbol.id); }} />)}</g>
    </svg><div className="pid-editor-canvas-hint"><MoveIcon /> Kéo symbol để di chuyển · Lăn chuột để zoom · Kéo nền để pan</div></div></section>
  </main>;
}

function MoveIcon() {
  return <span aria-hidden="true" className="pid-editor-move-icon">✥</span>;
}
