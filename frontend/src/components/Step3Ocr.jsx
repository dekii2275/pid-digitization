import React, { useState } from 'react';
import { Search, Type } from 'lucide-react';
import { DrawingViewer } from './DrawingViewer';
import { api } from '../services/api';

export function Step3Ocr({ currentDrawing, ocrTexts = [], onOcrUpdated }) {
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedOcr, setSelectedOcr] = useState(null);
  const [editingId, setEditingId] = useState(null);
  const [editingText, setEditingText] = useState('');

  // Filter OCR texts by search query
  const filteredTexts = ocrTexts.filter((item) =>
    (item.text || '').toLowerCase().includes(searchTerm.toLowerCase())
  );

  const handleRowClick = (item) => {
    setSelectedOcr(item);
  };

  const handleStartEdit = (item, e) => {
    e.stopPropagation();
    setEditingId(item.id);
    setEditingText(item.text);
  };

  const handleSaveEdit = async (id, e) => {
    e.stopPropagation();
    try {
      await api.getOcrTexts(currentDrawing.id); // Or update API
      setEditingId(null);
      if (onOcrUpdated) onOcrUpdated();
    } catch (err) {
      alert('Lỗi lưu text: ' + err.message);
    }
  };

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1.1fr 0.9fr', gap: '1.25rem', height: 'calc(100vh - 125px)' }}>
      {/* Left: Drawing Viewer with OCR Overlays */}
      <div className="card" style={{ padding: '0.5rem', display: 'flex', flexDirection: 'column' }}>
        <div style={{
          padding: '0.5rem 0.75rem',
          borderBottom: '1px solid var(--border-color)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}>
          <span style={{ fontSize: '0.85rem', fontWeight: '600', color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Type size={16} color="var(--accent-cyan)" />
            Trực quan hóa Hộp Text OCR ({ocrTexts.length} mục)
          </span>
          {selectedOcr && (
            <span className="badge" style={{ background: 'rgba(245, 158, 11, 0.15)', color: 'var(--accent-amber)' }}>
              Đang chọn: "{selectedOcr.text}"
            </span>
          )}
        </div>

        <div style={{ flex: 1, minHeight: 0 }}>
          <DrawingViewer
            drawing={currentDrawing}
            ocrTexts={ocrTexts}
            showSymbols={false}
            showOcr={true}
            showLines={false}
            highlightedBox={selectedOcr ? [selectedOcr.bbox_x1, selectedOcr.bbox_y1, selectedOcr.bbox_x2, selectedOcr.bbox_y2] : null}
          />
        </div>
      </div>

      {/* Right: Searchable OCR Data Table (Section 3 of Mockup) */}
      <div className="card" style={{ display: 'flex', flexDirection: 'column', padding: '0.75rem' }}>
        {/* Table Search & Filter Bar */}
        <div style={{ marginBottom: '0.75rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', background: 'var(--bg-primary)', border: '1px solid var(--border-color)', borderRadius: '6px', padding: '0.4rem 0.75rem' }}>
            <Search size={16} color="var(--text-muted)" />
            <input
              type="text"
              placeholder="Tìm kiếm text hoặc tag (VD: T-101, P-101, 6&quot;-P-1001)..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              style={{
                background: 'transparent',
                border: 'none',
                color: '#fff',
                fontSize: '0.85rem',
                outline: 'none',
                width: '100%',
              }}
            />
          </div>
        </div>

        {/* Scrollable Table */}
        <div style={{ flex: 1, overflowY: 'auto', border: '1px solid var(--border-color)', borderRadius: '6px' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem', textAlign: 'left' }}>
            <thead style={{ background: 'var(--bg-primary)', position: 'sticky', top: 0, zIndex: 10, borderBottom: '1px solid var(--border-color)' }}>
              <tr>
                <th style={{ padding: '0.6rem 0.75rem', color: 'var(--text-secondary)', fontWeight: '600' }}>Text</th>
                <th style={{ padding: '0.6rem 0.75rem', color: 'var(--text-secondary)', fontWeight: '600' }}>Bounding Box [x1, y1, x2, y2]</th>
                <th style={{ padding: '0.6rem 0.75rem', color: 'var(--text-secondary)', fontWeight: '600' }}>Confidence</th>
                <th style={{ padding: '0.6rem 0.75rem', color: 'var(--text-secondary)', fontWeight: '600' }}>Engine</th>
              </tr>
            </thead>
            <tbody>
              {filteredTexts.length === 0 ? (
                <tr>
                  <td colSpan={4} style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                    Không tìm thấy text nào khớp với từ khóa.
                  </td>
                </tr>
              ) : (
                filteredTexts.map((item) => {
                  const isSelected = selectedOcr?.id === item.id;
                  const isEditing = editingId === item.id;

                  return (
                    <tr
                      key={item.id}
                      onClick={() => handleRowClick(item)}
                      style={{
                        background: isSelected ? 'rgba(14, 165, 233, 0.15)' : 'transparent',
                        borderBottom: '1px solid rgba(51, 65, 85, 0.5)',
                        cursor: 'pointer',
                        transition: 'background 0.1s ease',
                      }}
                    >
                      <td style={{ padding: '0.5rem 0.75rem', fontWeight: '600', color: isSelected ? 'var(--accent-cyan)' : '#fff', fontFamily: 'var(--font-mono)' }}>
                        {isEditing ? (
                          <input
                            type="text"
                            value={editingText}
                            onChange={(e) => setEditingText(e.target.value)}
                            onBlur={(e) => handleSaveEdit(item.id, e)}
                            autoFocus
                            style={{
                              background: 'var(--bg-primary)',
                              border: '1px solid var(--accent-cyan)',
                              borderRadius: '4px',
                              color: '#fff',
                              padding: '0.2rem 0.4rem',
                              fontSize: '0.8rem',
                            }}
                          />
                        ) : (
                          <span onDoubleClick={(e) => handleStartEdit(item, e)} title="Nhấp đúp để sửa">
                            {item.text}
                          </span>
                        )}
                      </td>
                      <td style={{ padding: '0.5rem 0.75rem', color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)', fontSize: '0.75rem' }}>
                        [{Math.round(item.bbox_x1)}, {Math.round(item.bbox_y1)}, {Math.round(item.bbox_x2)}, {Math.round(item.bbox_y2)}]
                      </td>
                      <td style={{ padding: '0.5rem 0.75rem' }}>
                        <span className="badge" style={{
                          background: item.confidence > 0.9 ? 'rgba(16, 185, 129, 0.15)' : 'rgba(245, 158, 11, 0.15)',
                          color: item.confidence > 0.9 ? 'var(--accent-green)' : 'var(--accent-amber)',
                        }}>
                          {(item.confidence * 100).toFixed(0)}%
                        </span>
                      </td>
                      <td style={{ padding: '0.5rem 0.75rem', color: 'var(--text-muted)' }}>
                        {item.ocr_engine || 'PP-OCRv5'}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Footer Info */}
        <div style={{ marginTop: '0.5rem', fontSize: '0.75rem', color: 'var(--text-muted)', display: 'flex', justifyContent: 'space-between' }}>
          <span>Hiển thị {filteredTexts.length} / {ocrTexts.length} chuỗi văn bản</span>
          <span>Nhấp vào một dòng để phóng tới vị trí trên bản vẽ</span>
        </div>
      </div>
    </div>
  );
}
