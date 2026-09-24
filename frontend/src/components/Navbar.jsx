import React, { useState, useEffect, useCallback } from 'react';
import { Layers, FileText, CheckCircle2, AlertCircle, RefreshCw } from 'lucide-react';
import { api } from '../services/api';

export function Navbar({ currentDrawing, onSelectDrawing, onNewDrawing }) {
  const [drawings, setDrawings] = useState([]);
  const [isBackendHealthy, setIsBackendHealthy] = useState(false);
  const [loading, setLoading] = useState(false);

  const fetchDrawingsList = useCallback(async () => {
    try {
      const data = await api.getDrawings();
      setDrawings(data);
      setIsBackendHealthy(true);
      if (data.length > 0 && !currentDrawing) {
        onSelectDrawing(data[0]);
      }
    } catch (err) {
      console.warn('Backend not responding yet:', err);
      setIsBackendHealthy(false);
    } finally {
      setLoading(false);
    }
  }, [currentDrawing, onSelectDrawing]);

  useEffect(() => {
    const initialFetch = setTimeout(fetchDrawingsList, 0);
    const interval = setInterval(fetchDrawingsList, 10000);
    return () => {
      clearTimeout(initialFetch);
      clearInterval(interval);
    };
  }, [fetchDrawingsList]);

  return (
    <header style={{
      background: 'var(--bg-secondary)',
      borderBottom: '1px solid var(--border-color)',
      padding: '0.75rem 1.5rem',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      position: 'sticky',
      top: 0,
      zIndex: 50,
    }}>
      {/* Brand & Project Title */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
        <div style={{
          width: '38px',
          height: '38px',
          borderRadius: '8px',
          background: 'linear-gradient(135deg, var(--accent-cyan), var(--accent-blue))',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'white',
          boxShadow: '0 4px 12px rgba(14, 165, 233, 0.3)'
        }}>
          <Layers size={22} />
        </div>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <h1 style={{ fontSize: '1.1rem', fontWeight: '700', letterSpacing: '-0.02em', color: '#fff' }}>
              vpi_detect_and_ocr
            </h1>
            <span className="badge" style={{ background: 'rgba(56, 189, 248, 0.15)', color: 'var(--accent-cyan)' }}>
              v1.0.0
            </span>
          </div>
          <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
            Nền tảng Số hóa Bản vẽ Kỹ thuật P&ID / PFD thành Đồ thị Cấu trúc
          </p>
        </div>
      </div>

      {/* Drawing Selector & Controls */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <FileText size={16} color="var(--text-muted)" />
          <select
            value={currentDrawing?.id || ''}
            onChange={(e) => {
              const selected = drawings.find((d) => d.id === parseInt(e.target.value));
              if (selected) onSelectDrawing(selected);
            }}
            style={{
              background: 'var(--bg-card)',
              color: 'var(--text-primary)',
              border: '1px solid var(--border-color)',
              borderRadius: '6px',
              padding: '0.4rem 0.8rem',
              fontSize: '0.85rem',
              outline: 'none',
              cursor: 'pointer',
              minWidth: '220px',
            }}
          >
            {drawings.length === 0 && <option value="">Chưa có bản vẽ nào</option>}
            {drawings.map((d) => (
              <option key={d.id} value={d.id}>
                #{d.id} - {d.name} ({d.status})
              </option>
            ))}
          </select>

          <button
            className="btn btn-secondary btn-sm"
            onClick={() => {
              setLoading(true);
              fetchDrawingsList();
            }}
            title="Làm mới danh sách"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>

        <button
          className="btn btn-primary btn-sm"
          onClick={onNewDrawing}
        >
          + Tải lên P&ID mới
        </button>

        {/* Backend Status Indicator */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.4rem',
          padding: '0.3rem 0.6rem',
          borderRadius: '9999px',
          background: isBackendHealthy ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)',
          border: `1px solid ${isBackendHealthy ? 'rgba(16, 185, 129, 0.3)' : 'rgba(239, 68, 68, 0.3)'}`,
          fontSize: '0.75rem',
          fontWeight: '500',
          color: isBackendHealthy ? 'var(--accent-green)' : 'var(--accent-red)',
        }}>
          {isBackendHealthy ? <CheckCircle2 size={13} /> : <AlertCircle size={13} />}
          <span>{isBackendHealthy ? 'API Online' : 'API Offline'}</span>
        </div>
      </div>
    </header>
  );
}
