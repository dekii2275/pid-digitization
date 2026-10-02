import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react';

const clamp = (value, minimum, maximum) => Math.min(Math.max(value, minimum), maximum);

const symbolColors = ['#e67e22', '#0070c0', '#c0392b', '#239b56', '#7b3fb2'];

const asPoint = (value) => {
  if (Array.isArray(value) && value.length >= 2) return [Number(value[0]), Number(value[1])];
  if (value && typeof value === 'object') return [Number(value.x), Number(value.y)];
  return null;
};

const pointsFromSegment = (segment) => {
  if (Array.isArray(segment)) return segment.map(asPoint).filter((point) => point?.every(Number.isFinite));
  if (!segment || typeof segment !== 'object') return [];
  if (Array.isArray(segment.points)) return segment.points.map(asPoint).filter((point) => point?.every(Number.isFinite));
  const start = asPoint(segment.start ?? [segment.x1, segment.y1]);
  const end = asPoint(segment.end ?? [segment.x2, segment.y2]);
  return start?.every(Number.isFinite) && end?.every(Number.isFinite) ? [start, end] : [];
};

const pathForPoints = (points, scale) => points.length > 1
  ? points.map(([x, y], index) => `${index ? 'L' : 'M'} ${x * scale} ${y * scale}`).join(' ')
  : null;

const TiledDrawingCanvas = forwardRef(function TiledDrawingCanvas({ drawing, results, showDetections, showTags, showConnections, reviewMode = false, selectedItem, onSelectItem, onUpdateItem, onCreateItem, drawMode = null, onZoomChange }, ref) {
  const containerRef = useRef(null);
  const dragRef = useRef(null);
  const editRef = useRef(null);
  const createRef = useRef(null);
  const [viewport, setViewport] = useState({ width: 0, height: 0 });
  const [view, setView] = useState({ scale: 1, x: 0, y: 0 });
  const [draftBox, setDraftBox] = useState(null);

  const fitDrawing = () => {
    const container = containerRef.current;
    if (!container) return;
    const { width, height } = container.getBoundingClientRect();
    if (!width || !height) return;
    const scale = Math.min(width / drawing.width, height / drawing.height) * 0.92;
    setView({ scale, x: (width - drawing.width * scale) / 2, y: (height - drawing.height * scale) / 2 });
  };

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return undefined;
    const observer = new ResizeObserver(([entry]) => setViewport({ width: entry.contentRect.width, height: entry.contentRect.height }));
    observer.observe(container);
    return () => observer.disconnect();
  }, []);
  useEffect(() => { fitDrawing(); }, [drawing.id, viewport.width, viewport.height]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { onZoomChange?.(Math.round(view.scale * 100)); }, [onZoomChange, view.scale]);

  const zoomAt = (nextScale, clientX, clientY) => {
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return;
    const targetScale = clamp(nextScale, 0.03, 8);
    const pointerX = clientX - rect.left;
    const pointerY = clientY - rect.top;
    setView((current) => {
      const worldX = (pointerX - current.x) / current.scale;
      const worldY = (pointerY - current.y) / current.scale;
      return { scale: targetScale, x: pointerX - worldX * targetScale, y: pointerY - worldY * targetScale };
    });
  };
  const zoomBy = (factor) => {
    const rect = containerRef.current?.getBoundingClientRect();
    if (rect) zoomAt(view.scale * factor, rect.left + rect.width / 2, rect.top + rect.height / 2);
  };
  useImperativeHandle(ref, () => ({ zoomIn: () => zoomBy(1.25), zoomOut: () => zoomBy(0.8), fit: fitDrawing }), [view.scale]); // eslint-disable-line react-hooks/exhaustive-deps

  // Prefer a sharper tile level over the smallest possible download. P&ID drawings
  // contain thin lines and small tags that become visibly smeared when downsampled.
  const tileLevel = clamp(Math.ceil(drawing.max_zoom + Math.log2(view.scale)) + 1, 0, drawing.max_zoom);
  const sourceScale = 2 ** (tileLevel - drawing.max_zoom);
  const screenScale = view.scale / sourceScale;
  const levelWidth = Math.ceil(drawing.width * sourceScale);
  const levelHeight = Math.ceil(drawing.height * sourceScale);
  const tiles = useMemo(() => {
    if (!viewport.width || !viewport.height) return [];
    const countX = Math.ceil(levelWidth / drawing.tile_size);
    const countY = Math.ceil(levelHeight / drawing.tile_size);
    const firstX = clamp(Math.floor((-view.x / screenScale) / drawing.tile_size) - 1, 0, countX);
    const firstY = clamp(Math.floor((-view.y / screenScale) / drawing.tile_size) - 1, 0, countY);
    const lastX = clamp(Math.ceil(((viewport.width - view.x) / screenScale) / drawing.tile_size) + 1, 0, countX);
    const lastY = clamp(Math.ceil(((viewport.height - view.y) / screenScale) / drawing.tile_size) + 1, 0, countY);
    const visible = [];
    for (let y = firstY; y < lastY; y += 1) for (let x = firstX; x < lastX; x += 1) visible.push({ x, y });
    return visible;
  }, [drawing.tile_size, levelHeight, levelWidth, screenScale, viewport.height, viewport.width, view.x, view.y]);
  const tileUrl = (x, y) => drawing.tile_url_template.replace('{z}', tileLevel).replace('{x}', x).replace('{y}', y);
  const detectedSymbols = results?.symbols || [];
  const recognizedTexts = results?.texts || [];
  const detectedLines = results?.lines || [];
  const topologyEdges = results?.topology_edges || [];
  const symbolsById = new Map(detectedSymbols.map((symbol) => [String(symbol.id), symbol]));
  const overlayStroke = 2 / Math.max(screenScale, 0.001);
  const selected = (kind, id) => selectedItem?.kind === kind && String(selectedItem.id) === String(id);
  const isReviewEditing = reviewMode && !showDetections;
  const isEditingItem = (kind, id) => isReviewEditing && selected(kind, id);
  const notifySelection = (kind, item) => onSelectItem?.({ kind, id: item.id });

  const pointFromEvent = (event) => {
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return null;
    return {
      x: clamp((event.clientX - rect.left - view.x) / Math.max(view.scale, 0.001), 0, drawing.width),
      y: clamp((event.clientY - rect.top - view.y) / Math.max(view.scale, 0.001), 0, drawing.height),
    };
  };

  const rectFromPoints = (start, current) => ({
    x: Math.min(start.x, current.x),
    y: Math.min(start.y, current.y),
    width: Math.abs(current.x - start.x),
    height: Math.abs(current.y - start.y),
  });

  const selectOnly = (event, kind, item) => {
    if (!reviewMode) return;
    event.preventDefault();
    event.stopPropagation();
    notifySelection(kind, item);
  };

  const startEdit = (event, kind, item, mode = 'move') => {
    // In manual drawing mode the canvas owns the pointer gesture. This lets a
    // reviewer draw a new box even when the gesture starts over an existing
    // detection or OCR label.
    if (drawMode) return;
    if (!isEditingItem(kind, item.id)) { selectOnly(event, kind, item); return; }
    event.preventDefault();
    event.stopPropagation();
    event.currentTarget.setPointerCapture?.(event.pointerId);
    notifySelection(kind, item);
    editRef.current = { pointerId: event.pointerId, kind, item: { ...item }, mode, clientX: event.clientX, clientY: event.clientY };
  };

  const moveEditedItem = (event) => {
    const edit = editRef.current;
    if (!edit || edit.pointerId !== event.pointerId) return false;
    const dx = (event.clientX - edit.clientX) / view.scale;
    const dy = (event.clientY - edit.clientY) / view.scale;
    if (edit.kind === 'symbol') {
      const start = edit.item;
      let x = Number(start.x) || 0;
      let y = Number(start.y) || 0;
      let width = Math.max(4, Number(start.width) || 4);
      let height = Math.max(4, Number(start.height) || 4);
      if (edit.mode === 'move') { x += dx; y += dy; }
      if (edit.mode !== 'move' && edit.mode.includes('e')) width = Math.max(4, width + dx);
      if (edit.mode !== 'move' && edit.mode.includes('s')) height = Math.max(4, height + dy);
      if (edit.mode !== 'move' && edit.mode.includes('w')) { const nextWidth = Math.max(4, width - dx); x += width - nextWidth; width = nextWidth; }
      if (edit.mode !== 'move' && edit.mode.includes('n')) { const nextHeight = Math.max(4, height - dy); y += height - nextHeight; height = nextHeight; }
      onUpdateItem?.('symbol', start.id, { x: clamp(x, 0, Math.max(0, drawing.width - width)), y: clamp(y, 0, Math.max(0, drawing.height - height)), width, height });
    } else if (edit.kind === 'text') {
      const start = edit.item;
      onUpdateItem?.('text', start.id, { x: clamp((Number(start.x) || 0) + dx, 0, drawing.width), y: clamp((Number(start.y) || 0) + dy, 0, drawing.height) });
    } else if (edit.kind === 'line') {
      const start = edit.item;
      if (Array.isArray(start.start) && Array.isArray(start.end)) {
        onUpdateItem?.('line', start.id, { start: [start.start[0] + dx, start.start[1] + dy], end: [start.end[0] + dx, start.end[1] + dy] });
      } else {
        onUpdateItem?.('line', start.id, { x1: (Number(start.x1) || 0) + dx, y1: (Number(start.y1) || 0) + dy, x2: (Number(start.x2) || 0) + dx, y2: (Number(start.y2) || 0) + dy });
      }
    }
    return true;
  };

  return <div className={`tiled-drawing-canvas ${drawMode ? 'is-drawing' : ''}`} ref={containerRef}
    onWheel={(event) => { event.preventDefault(); zoomAt(view.scale * (event.deltaY < 0 ? 1.18 : 0.85), event.clientX, event.clientY); }}
    onPointerDown={(event) => {
      if (drawMode && event.button === 0) {
        const point = pointFromEvent(event);
        if (!point) return;
        event.preventDefault();
        event.stopPropagation();
        createRef.current = { pointerId: event.pointerId, start: point };
        setDraftBox({ ...point, width: 0, height: 0 });
        event.currentTarget.setPointerCapture(event.pointerId);
        return;
      }
      dragRef.current = { pointerId: event.pointerId, x: event.clientX, y: event.clientY, view };
      event.currentTarget.setPointerCapture(event.pointerId);
    }}
    onPointerMove={(event) => {
      const create = createRef.current;
      if (create?.pointerId === event.pointerId) {
        const point = pointFromEvent(event);
        if (point) setDraftBox(rectFromPoints(create.start, point));
        return;
      }
      if (moveEditedItem(event)) return;
      const drag = dragRef.current;
      if (drag?.pointerId === event.pointerId) setView({ ...drag.view, x: drag.view.x + event.clientX - drag.x, y: drag.view.y + event.clientY - drag.y });
    }}
    onPointerUp={(event) => {
      const create = createRef.current;
      if (create?.pointerId === event.pointerId) {
        const point = pointFromEvent(event);
        const box = point ? rectFromPoints(create.start, point) : null;
        createRef.current = null;
        setDraftBox(null);
        if (box && box.width >= 6 && box.height >= 6) onCreateItem?.(drawMode, box);
        return;
      }
      dragRef.current = null;
    }}
    onPointerCancel={(event) => {
      if (createRef.current?.pointerId === event.pointerId) {
        createRef.current = null;
        setDraftBox(null);
      }
      dragRef.current = null;
    }}
    aria-label="Bản vẽ P&ID, kéo để pan và lăn chuột để zoom">
    <div className={`tiled-drawing-layer ${isReviewEditing ? 'review-is-editing' : ''}`} style={{ width: levelWidth, height: levelHeight, transform: `translate(${view.x}px, ${view.y}px) scale(${screenScale})` }}>
      {tiles.map(({ x, y }) => <img key={`${tileLevel}-${x}-${y}`} className="drawing-tile" draggable="false" src={tileUrl(x, y)} alt="" style={{ left: x * drawing.tile_size, top: y * drawing.tile_size, width: Math.min(drawing.tile_size, levelWidth - x * drawing.tile_size), height: Math.min(drawing.tile_size, levelHeight - y * drawing.tile_size) }} />)}
      {showConnections && <svg className="connection-overlay" width={levelWidth} height={levelHeight} viewBox={`0 0 ${levelWidth} ${levelHeight}`} aria-label="Đường kết nối do AI xử lý">
        <g className="connection-overlay__detected-lines">
          {detectedLines.map((line, index) => {
            const path = pathForPoints(pointsFromSegment(line), sourceScale);
            return path && <path key={line.id || index} d={path} strokeWidth={overlayStroke} pointerEvents={reviewMode ? 'stroke' : 'none'} className={selected('line', line.id) ? 'is-selected' : ''} onPointerDown={(event) => startEdit(event, 'line', line)} onClick={(event) => { if (drawMode) { event.preventDefault(); event.stopPropagation(); return; } notifySelection('line', line); }} />;
          })}
        </g>
        <g className="connection-overlay__topology">
          {topologyEdges.map((edge, index) => {
            const segmentPaths = (edge.segments || []).map((segment) => pathForPoints(pointsFromSegment(segment), sourceScale)).filter(Boolean);
            if (segmentPaths.length) return segmentPaths.map((path, segmentIndex) => <path key={`${edge.id || index}-${segmentIndex}`} d={path} strokeWidth={overlayStroke} pointerEvents={reviewMode ? 'stroke' : 'none'} className={selected('connection', edge.id) ? 'is-selected' : ''} onClick={(event) => { if (!drawMode) notifySelection('connection', edge); else { event.preventDefault(); event.stopPropagation(); } }} />);
            const source = symbolsById.get(String(edge.source));
            const target = symbolsById.get(String(edge.target));
            if (!source || !target) return null;
            const sourceX = (Number(source.x) + Number(source.width) / 2) * sourceScale;
            const sourceY = (Number(source.y) + Number(source.height) / 2) * sourceScale;
            const targetX = (Number(target.x) + Number(target.width) / 2) * sourceScale;
            const targetY = (Number(target.y) + Number(target.height) / 2) * sourceScale;
            return <path key={edge.id || index} d={`M ${sourceX} ${sourceY} L ${targetX} ${targetY}`} strokeWidth={overlayStroke} pointerEvents={reviewMode ? 'stroke' : 'none'} className={selected('connection', edge.id) ? 'is-selected' : ''} onClick={(event) => { if (!drawMode) notifySelection('connection', edge); else { event.preventDefault(); event.stopPropagation(); } }} />;
          })}
        </g>
      </svg>}
      {reviewMode && detectedSymbols.map((symbol, index) => { const label = symbol.tag || symbol.type || 'Symbol'; return <button key={`edit-${symbol.id || index}`} className={`detection-box review-detection-editor ${selected('symbol', symbol.id) ? 'is-selected' : ''}`} style={{ '--box-color': symbolColors[index % symbolColors.length], left: Number(symbol.x) * sourceScale, top: Number(symbol.y) * sourceScale, width: Number(symbol.width) * sourceScale, height: Number(symbol.height) * sourceScale }} onPointerDown={(event) => startEdit(event, 'symbol', symbol)} onClick={(event) => { if (!drawMode) notifySelection('symbol', symbol); else { event.preventDefault(); event.stopPropagation(); } }} title={`${label} · ${symbol.id || 'Symbol'}`}><span>{label}</span><i className="bbox-handle bbox-handle--nw" onPointerDown={(event) => startEdit(event, 'symbol', symbol, 'nw')} /><i className="bbox-handle bbox-handle--ne" onPointerDown={(event) => startEdit(event, 'symbol', symbol, 'ne')} /><i className="bbox-handle bbox-handle--sw" onPointerDown={(event) => startEdit(event, 'symbol', symbol, 'sw')} /><i className="bbox-handle bbox-handle--se" onPointerDown={(event) => startEdit(event, 'symbol', symbol, 'se')} /></button>; })}
      {reviewMode && recognizedTexts.map((text, index) => <button key={`edit-text-${text.id || index}`} className={`review-text-editor ${selected('text', text.id) ? 'is-selected' : ''}`} style={{ left: Number(text.x) * sourceScale, top: Number(text.y) * sourceScale, width: Number(text.width) * sourceScale, height: Number(text.height) * sourceScale }} onPointerDown={(event) => startEdit(event, 'text', text)} onClick={(event) => { if (!drawMode) notifySelection('text', text); else { event.preventDefault(); event.stopPropagation(); } }}>{text.text}</button>)}
      {showDetections && detectedSymbols.map((symbol, index) => <button key={symbol.id || index} className="detection-box pipeline-detection" style={{ '--box-color': symbolColors[index % symbolColors.length], left: Number(symbol.x) * sourceScale, top: Number(symbol.y) * sourceScale, width: Number(symbol.width) * sourceScale, height: Number(symbol.height) * sourceScale }} title={`${symbol.type || 'Symbol'} · ${Math.round(Number(symbol.confidence || 0) * 100)}%`}><span>{symbol.type || 'Symbol'}</span></button>)}
      {showTags && recognizedTexts.map((text, index) => <div key={text.id || index} className="pipeline-tag" style={{ left: Number(text.x) * sourceScale, top: Number(text.y) * sourceScale, width: Number(text.width) * sourceScale, height: Number(text.height) * sourceScale }} title={text.text}>{text.text}</div>)}
      {draftBox && <div className="manual-box-draft" style={{ left: draftBox.x * sourceScale, top: draftBox.y * sourceScale, width: draftBox.width * sourceScale, height: draftBox.height * sourceScale }}><span>{drawMode === 'text' ? 'OCR' : 'Symbol'}</span></div>}
    </div>
    <div className="viewer-hint">Kéo để di chuyển · Lăn chuột để phóng to/thu nhỏ · Tile L{tileLevel}</div>
  </div>;
});

export default TiledDrawingCanvas;
