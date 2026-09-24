import React, { useState } from 'react';
import { Sliders, Trash2, Tag } from 'lucide-react';
import { DrawingViewer } from './DrawingViewer';
import { api } from '../services/api';

export function Step2Detection({ currentDrawing, symbols = [], onSymbolsUpdated }) {
  const [minConf, setMinConf] = useState(0.15);
  const [selectedSymbol, setSelectedSymbol] = useState(null);
  const [editingTag, setEditingTag] = useState('');
  const [visibleCategories, setVisibleCategories] = useState({
    Equipment: true,
    Pump: true,
    Valve: true,
    Instrument: true,
    Line: true,
    Other: true,
  });

  const categoryConfigs = [
    { key: 'Equipment', label: 'Equipment (Thiết bị)', color: 'var(--color-equipment)' },
    { key: 'Pump', label: 'Pump (Bơm)', color: 'var(--color-pump)' },
    { key: 'Valve', label: 'Valve (Van)', color: 'var(--color-valve)' },
    { key: 'Instrument', label: 'Instrument (Thiết bị đo)', color: 'var(--color-instrument)' },
    { key: 'Line', label: 'Line (Đường ống)', color: 'var(--color-line)' },
  ];

  const toggleCategory = (cat) => {
    setVisibleCategories((prev) => ({ ...prev, [cat]: !prev[cat] }));
  };

  // Count symbols by category
  const categoryCounts = symbols.reduce((acc, s) => {
    const cat = s.category || 'Other';
    acc[cat] = (acc[cat] || 0) + 1;
    return acc;
  }, {});

  const handleSelectSymbol = (sym) => {
    setSelectedSymbol(sym);
    setEditingTag(sym.tag || '');
  };

  const handleSaveTag = async () => {
    if (!selectedSymbol) return;
    try {
      const updated = await api.updateSymbol(selectedSymbol.id, { tag: editingTag });
      setSelectedSymbol(updated);
      if (onSymbolsUpdated) onSymbolsUpdated();
    } catch (err) {
      alert('Lỗi cập nhật nhãn: ' + err.message);
    }
  };

  const handleDeleteSymbol = async () => {
    if (!selectedSymbol) return;
    if (!confirm(`Bạn có chắc muốn xóa symbol #${selectedSymbol.id}?`)) return;
    try {
      await api.deleteSymbol(selectedSymbol.id);
      setSelectedSymbol(null);
      if (onSymbolsUpdated) onSymbolsUpdated();
    } catch (err) {
      alert('Lỗi xóa symbol: ' + err.message);
    }
  };

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: '1.25rem', height: 'calc(100vh - 125px)' }}>
      {/* Left: Drawing Canvas with 5-color detection overlay */}
      <div className="card" style={{ padding: '0.5rem', display: 'flex', flexDirection: 'column' }}>
        {/* Top Filter Bar */}
        <div style={{
          padding: '0.5rem 0.75rem',
          borderBottom: '1px solid var(--border-color)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '0.75rem',
        }}>
          {/* 5-Color Legend Checkboxes */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
            {categoryConfigs.map((cfg) => {
              const isChecked = visibleCategories[cfg.key];
              const count = categoryCounts[cfg.key] || 0;

              return (
                <button
                  key={cfg.key}
                  onClick={() => toggleCategory(cfg.key)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.35rem',
                    background: isChecked ? 'rgba(30, 41, 59, 0.8)' : 'transparent',
                    border: `1px solid ${isChecked ? cfg.color : 'var(--border-color)'}`,
                    borderRadius: '6px',
                    padding: '0.25rem 0.6rem',
                    color: isChecked ? '#fff' : 'var(--text-muted)',
                    fontSize: '0.75rem',
                    cursor: 'pointer',
                    transition: 'all 0.15s ease',
                  }}
                >
                  <span style={{
                    width: '10px',
                    height: '10px',
                    borderRadius: '2px',
                    background: cfg.color,
                  }} />
                  <span style={{ fontWeight: '500' }}>{cfg.label.split(' ')[0]}</span>
                  <span className="badge" style={{ background: `${cfg.color}25`, color: cfg.color, padding: '0.1rem 0.35rem' }}>
                    {count}
                  </span>
                </button>
              );
            })}
          </div>

          {/* Confidence Slider */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Sliders size={15} color="var(--text-muted)" />
            <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
              Confidence ≥ {minConf}
            </span>
            <input
              type="range"
              min="0.0"
              max="0.9"
              step="0.05"
              value={minConf}
              onChange={(e) => setMinConf(parseFloat(e.target.value))}
              style={{ width: '90px' }}
            />
          </div>
        </div>

        {/* Canvas Viewer */}
        <div style={{ flex: 1, minHeight: 0 }}>
          <DrawingViewer
            drawing={currentDrawing}
            symbols={symbols}
            showSymbols={true}
            showOcr={false}
            showLines={false}
            visibleCategories={visibleCategories}
            minConfidence={minConf}
            highlightedBox={selectedSymbol ? [selectedSymbol.bbox_x1, selectedSymbol.bbox_y1, selectedSymbol.bbox_x2, selectedSymbol.bbox_y2] : null}
            onSelectSymbol={handleSelectSymbol}
          />
        </div>
      </div>

      {/* Right: Selected Symbol Inspector & Editor */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        <div className="card" style={{ height: '100%', overflowY: 'auto' }}>
          <h2 style={{ fontSize: '1rem', fontWeight: '600', marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Tag size={18} color="var(--accent-cyan)" />
            Chi tiết Đối tượng (Inspector)
          </h2>

          {selectedSymbol ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div>
                <label style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Loại thiết bị (Class):</label>
                <div style={{ fontSize: '0.9rem', fontWeight: '600', color: '#fff', marginTop: '0.2rem' }}>
                  {selectedSymbol.class_name}
                </div>
              </div>

              <div>
                <label style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Nhóm phân loại (Category):</label>
                <div style={{ marginTop: '0.2rem' }}>
                  <span className="badge" style={{
                    background: `${categoryConfigs.find(c => c.key === selectedSymbol.category)?.color || '#94a3b8'}20`,
                    color: categoryConfigs.find(c => c.key === selectedSymbol.category)?.color || '#fff',
                    border: `1px solid ${categoryConfigs.find(c => c.key === selectedSymbol.category)?.color || '#94a3b8'}`,
                  }}>
                    {selectedSymbol.category}
                  </span>
                </div>
              </div>

              <div>
                <label style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Độ tin cậy (Confidence):</label>
                <div style={{ fontSize: '0.85rem', color: 'var(--text-primary)', marginTop: '0.2rem' }}>
                  {(selectedSymbol.confidence * 100).toFixed(1)}%
                </div>
              </div>

              <div>
                <label style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Tọa độ Bounding Box [x1, y1, x2, y2]:</label>
                <div style={{
                  fontSize: '0.75rem',
                  fontFamily: 'var(--font-mono)',
                  color: 'var(--accent-cyan)',
                  background: 'var(--bg-primary)',
                  padding: '0.4rem 0.6rem',
                  borderRadius: '6px',
                  marginTop: '0.2rem',
                }}>
                  [{Math.round(selectedSymbol.bbox_x1)}, {Math.round(selectedSymbol.bbox_y1)}, {Math.round(selectedSymbol.bbox_x2)}, {Math.round(selectedSymbol.bbox_y2)}]
                </div>
              </div>

              {/* Tag Editing (Human-in-the-loop) */}
              <div style={{ borderTop: '1px solid var(--border-color)', paddingTop: '1rem' }}>
                <label style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '0.25rem' }}>
                  Gán Nhãn / Tag Kỹ thuật:
                </label>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <input
                    type="text"
                    value={editingTag}
                    onChange={(e) => setEditingTag(e.target.value)}
                    placeholder="VD: P-101, V-102"
                    style={{
                      flex: 1,
                      background: 'var(--bg-primary)',
                      border: '1px solid var(--border-color)',
                      borderRadius: '6px',
                      padding: '0.4rem 0.6rem',
                      color: '#fff',
                      fontSize: '0.85rem',
                      outline: 'none',
                    }}
                  />
                  <button className="btn btn-primary btn-sm" onClick={handleSaveTag}>
                    Lưu
                  </button>
                </div>
              </div>

              {/* Delete Symbol */}
              <div style={{ marginTop: '1rem' }}>
                <button
                  className="btn btn-secondary btn-sm"
                  style={{ width: '100%', borderColor: 'rgba(239, 68, 68, 0.4)', color: 'var(--accent-red)' }}
                  onClick={handleDeleteSymbol}
                >
                  <Trash2 size={15} /> Xóa Symbol này
                </button>
              </div>
            </div>
          ) : (
            <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem', textAlign: 'center', marginTop: '3rem' }}>
              Nhấp vào một symbol trên bản vẽ để xem thông tin chi tiết và chỉnh sửa nhãn.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
