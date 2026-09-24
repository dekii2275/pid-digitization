import React, { useState, useRef, useEffect } from 'react';
import { ZoomIn, ZoomOut, RotateCcw } from 'lucide-react';
import { api } from '../services/api';

export function DrawingViewer({
  drawing,
  symbols = [],
  ocrTexts = [],
  lines = [],
  showSymbols = true,
  showOcr = false,
  showLines = false,
  visibleCategories = {
    Equipment: true,
    Pump: true,
    Valve: true,
    Instrument: true,
    Line: true,
    Other: true,
  },
  minConfidence = 0.0,
  highlightedBox = null,
  onSelectSymbol = null,
}) {
  const containerRef = useRef(null);
  const [scale, setScale] = useState(1);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });

  const imageUrl = drawing ? api.getImageUrl(drawing.file_path) : '';
  const imgWidth = drawing?.width || 7168;
  const imgHeight = drawing?.height || 4561;

  // Reset or Fit view on drawing change
  useEffect(() => {
    if (containerRef.current && imgWidth) {
      const containerW = containerRef.current.clientWidth;
      const initialScale = Math.min(containerW / imgWidth, 0.8) || 0.2;
      setScale(initialScale);
      setPosition({ x: 20, y: 20 });
    }
  }, [drawing?.id, imgWidth]);

  // Pan handlers
  const handleMouseDown = (e) => {
    if (e.button !== 0) return; // only left click
    setIsDragging(true);
    setDragStart({ x: e.clientX - position.x, y: e.clientY - position.y });
  };

  const handleMouseMove = (e) => {
    if (!isDragging) return;
    setPosition({
      x: e.clientX - dragStart.x,
      y: e.clientY - dragStart.y,
    });
  };

  const handleMouseUp = () => setIsDragging(false);

  // Zoom handlers
  const handleWheel = (e) => {
    e.preventDefault();
    const zoomFactor = 1.15;
    const delta = e.deltaY < 0 ? zoomFactor : 1 / zoomFactor;
    const newScale = Math.min(Math.max(scale * delta, 0.05), 10);
    setScale(newScale);
  };

  const zoomIn = () => setScale((s) => Math.min(s * 1.25, 10));
  const zoomOut = () => setScale((s) => Math.max(s / 1.25, 0.05));
  const resetView = () => {
    if (containerRef.current) {
      const containerW = containerRef.current.clientWidth;
      const initialScale = Math.min(containerW / imgWidth, 0.8) || 0.2;
      setScale(initialScale);
      setPosition({ x: 20, y: 20 });
    }
  };

  // Color mapping helper
  const getCategoryColor = (category) => {
    switch (category) {
      case 'Equipment': return 'var(--color-equipment)';
      case 'Pump': return 'var(--color-pump)';
      case 'Valve': return 'var(--color-valve)';
      case 'Instrument': return 'var(--color-instrument)';
      case 'Line': return 'var(--color-line)';
      default: return '#94a3b8';
    }
  };

  // Filter symbols based on category & confidence
  const filteredSymbols = symbols.filter(
    (s) => visibleCategories[s.category] !== false && s.confidence >= minConfidence
  );

  return (
    <div
      ref={containerRef}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
      onWheel={handleWheel}
      style={{
        position: 'relative',
        width: '100%',
        height: '100%',
        minHeight: '600px',
        overflow: 'hidden',
        background: '#090d16',
        cursor: isDragging ? 'grabbing' : 'grab',
        userSelect: 'none',
      }}
    >
      {/* Floating Zoom & Pan Controls */}
      <div style={{
        position: 'absolute',
        bottom: '1.25rem',
        right: '1.25rem',
        display: 'flex',
        flexDirection: 'column',
        gap: '0.4rem',
        zIndex: 20,
        background: 'rgba(30, 41, 59, 0.85)',
        backdropFilter: 'blur(8px)',
        border: '1px solid var(--border-color)',
        borderRadius: '8px',
        padding: '0.4rem',
        boxShadow: '0 8px 30px rgba(0,0,0,0.4)',
      }}>
        <button className="btn btn-secondary btn-sm" onClick={zoomIn} title="Phóng to">
          <ZoomIn size={16} />
        </button>
        <button className="btn btn-secondary btn-sm" onClick={zoomOut} title="Thu nhỏ">
          <ZoomOut size={16} />
        </button>
        <button className="btn btn-secondary btn-sm" onClick={resetView} title="Căn vừa màn hình">
          <RotateCcw size={16} />
        </button>
        <div style={{
          fontSize: '0.7rem',
          textAlign: 'center',
          color: 'var(--text-muted)',
          paddingTop: '0.2rem',
          fontWeight: 600,
        }}>
          {Math.round(scale * 100)}%
        </div>
      </div>

      {/* Transform Container with SVG Layer */}
      <div
        style={{
          transform: `translate(${position.x}px, ${position.y}px) scale(${scale})`,
          transformOrigin: '0 0',
          position: 'absolute',
          top: 0,
          left: 0,
          width: `${imgWidth}px`,
          height: `${imgHeight}px`,
          transition: isDragging ? 'none' : 'transform 0.05s ease-out',
        }}
      >
        {/* Background P&ID Drawing Image */}
        {imageUrl ? (
          <img
            src={imageUrl}
            alt={drawing?.name || 'P&ID'}
            style={{
              width: `${imgWidth}px`,
              height: `${imgHeight}px`,
              display: 'block',
              pointerEvents: 'none',
            }}
          />
        ) : (
          <div style={{
            width: `${imgWidth}px`,
            height: `${imgHeight}px`,
            background: '#131b2e',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--text-muted)',
            fontSize: '2rem',
          }}>
            Chưa có ảnh bản vẽ
          </div>
        )}

        {/* SVG Annotations Overlay */}
        <svg
          viewBox={`0 0 ${imgWidth} ${imgHeight}`}
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            width: `${imgWidth}px`,
            height: `${imgHeight}px`,
            pointerEvents: 'all',
          }}
        >
          {/* 1. Lines Overlay */}
          {showLines && lines.map((l) => {
            const points = l.geometry?.points || [];
            if (points.length < 2) return null;
            const pathD = points.reduce(
              (acc, pt, i) => (i === 0 ? `M ${pt[0]} ${pt[1]}` : `${acc} L ${pt[0]} ${pt[1]}`),
              ''
            );
            return (
              <path
                key={`line-${l.id}`}
                d={pathD}
                stroke="var(--color-line)"
                strokeWidth={4 / scale}
                strokeLinecap="round"
                fill="none"
                opacity={0.85}
              />
            );
          })}

          {/* 2. Detected Symbols Overlay */}
          {showSymbols && filteredSymbols.map((sym) => {
            const color = getCategoryColor(sym.category);
            const w = Math.max(sym.bbox_x2 - sym.bbox_x1, 10);
            const h = Math.max(sym.bbox_y2 - sym.bbox_y1, 10);

            return (
              <g
                key={`sym-${sym.id}`}
                onClick={(e) => {
                  e.stopPropagation();
                  if (onSelectSymbol) onSelectSymbol(sym);
                }}
                style={{ cursor: 'pointer' }}
              >
                <rect
                  x={sym.bbox_x1}
                  y={sym.bbox_y1}
                  width={w}
                  height={h}
                  fill="transparent"
                  stroke={color}
                  strokeWidth={Math.max(2.5 / scale, 1.5)}
                  rx={2 / scale}
                />
              </g>
            );
          })}

          {/* 3. OCR Texts Overlay */}
          {showOcr && ocrTexts.map((txt) => {
            const w = Math.max(txt.bbox_x2 - txt.bbox_x1, 8);
            const h = Math.max(txt.bbox_y2 - txt.bbox_y1, 8);
            return (
              <g key={`ocr-${txt.id}`}>
                <rect
                  x={txt.bbox_x1}
                  y={txt.bbox_y1}
                  width={w}
                  height={h}
                  fill="rgba(14, 165, 233, 0.12)"
                  stroke="var(--accent-cyan)"
                  strokeWidth={1.5 / scale}
                  strokeDasharray={`${4 / scale}, ${2 / scale}`}
                  rx={2 / scale}
                />
                <text
                  x={txt.bbox_x1 + 2 / scale}
                  y={txt.bbox_y1 - 3 / scale}
                  fill="var(--accent-cyan)"
                  fontSize={`${9 / scale}px`}
                  fontWeight="500"
                  fontFamily="var(--font-mono)"
                >
                  {txt.text}
                </text>
              </g>
            );
          })}

          {/* 4. Highlighted Box (e.g. from OCR table selection) */}
          {highlightedBox && (
            <rect
              x={highlightedBox[0] - 6 / scale}
              y={highlightedBox[1] - 6 / scale}
              width={highlightedBox[2] - highlightedBox[0] + 12 / scale}
              height={highlightedBox[3] - highlightedBox[1] + 12 / scale}
              fill="rgba(245, 158, 11, 0.25)"
              stroke="var(--accent-amber)"
              strokeWidth={4 / scale}
              rx={4 / scale}
              className="animate-pulse-glow"
            />
          )}
        </svg>
      </div>
    </div>
  );
}
