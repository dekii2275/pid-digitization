import React, { useState } from 'react';
import { Upload, Play, Sliders } from 'lucide-react';
import { api } from '../services/api';
import { DrawingViewer } from './DrawingViewer';

export function Step1Input({ currentDrawing, onDrawingCreated, onProcessingStarted, isProcessing, progressInfo }) {
  const [file, setFile] = useState(null);
  const [drawingName, setDrawingName] = useState('');
  const [isUploading, setIsUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);

  // Parameter options
  const [dpi, setDpi] = useState(600);
  const [conf, setConf] = useState(0.15);
  const [tileSize, setTileSize] = useState(1024);
  const [device, setDevice] = useState('auto');

  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const droppedFile = e.dataTransfer.files[0];
      setFile(droppedFile);
      if (!drawingName) setDrawingName(droppedFile.name.replace(/\.[^/.]+$/, ''));
    }
  };

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files.length > 0) {
      const selectedFile = e.target.files[0];
      setFile(selectedFile);
      if (!drawingName) setDrawingName(selectedFile.name.replace(/\.[^/.]+$/, ''));
    }
  };

  const handleUploadAndRun = async () => {
    if (!file && !currentDrawing) return;
    try {
      setIsUploading(true);
      let targetDrawing = currentDrawing;

      if (file) {
        targetDrawing = await api.uploadDrawing(file, drawingName);
        onDrawingCreated(targetDrawing);
      }

      if (targetDrawing) {
        const job = await api.startProcessing(targetDrawing.id);
        onProcessingStarted(job.job_id, targetDrawing.id);
      }
    } catch (err) {
      alert('Lỗi khi tải lên hoặc khởi chạy xử lý: ' + err.message);
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '420px 1fr', gap: '1.25rem', height: 'calc(100vh - 125px)' }}>
      {/* Left Column: Upload & Configuration Panel */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', overflowY: 'auto' }}>
        {/* Upload Card */}
        <div className="card">
          <h2 style={{ fontSize: '1rem', fontWeight: '600', marginBottom: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Upload size={18} color="var(--accent-cyan)" />
            Tải lên Bản vẽ P&ID / PFD
          </h2>

          <div
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            style={{
              border: `2px dashed ${dragOver ? 'var(--accent-cyan)' : 'var(--border-color)'}`,
              borderRadius: '8px',
              padding: '1.75rem 1rem',
              textAlign: 'center',
              background: dragOver ? 'rgba(14, 165, 233, 0.05)' : 'var(--bg-primary)',
              cursor: 'pointer',
              transition: 'all 0.2s ease',
            }}
            onClick={() => document.getElementById('file-upload-input').click()}
          >
            <input
              id="file-upload-input"
              type="file"
              accept=".jpg,.jpeg,.png,.pdf"
              onChange={handleFileChange}
              style={{ display: 'none' }}
            />
            <div style={{
              width: '44px',
              height: '44px',
              borderRadius: '50%',
              background: 'rgba(56, 189, 248, 0.1)',
              color: 'var(--accent-cyan)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              margin: '0 auto 0.75rem',
            }}>
              <Upload size={22} />
            </div>
            <p style={{ fontSize: '0.875rem', fontWeight: '500', color: '#fff' }}>
              {file ? file.name : 'Kéo thả file hoặc nhấp để chọn'}
            </p>
            <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
              Hỗ trợ JPG, PNG, PDF vector và PDF scan
            </p>
          </div>

          <div style={{ marginTop: '0.75rem' }}>
            <label style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '0.25rem' }}>
              Tên bản vẽ:
            </label>
            <input
              type="text"
              value={drawingName}
              onChange={(e) => setDrawingName(e.target.value)}
              placeholder="VD: PID-101-Unit100"
              style={{
                width: '100%',
                background: 'var(--bg-primary)',
                border: '1px solid var(--border-color)',
                borderRadius: '6px',
                padding: '0.5rem 0.75rem',
                color: '#fff',
                fontSize: '0.85rem',
                outline: 'none',
              }}
            />
          </div>
        </div>

        {/* Pipeline Parameters Card */}
        <div className="card">
          <h2 style={{ fontSize: '1rem', fontWeight: '600', marginBottom: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Sliders size={18} color="var(--accent-blue)" />
            Cấu hình Tham số Pipeline
          </h2>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
            <div>
              <label style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>DPI Render (PDF):</label>
              <select
                value={dpi}
                onChange={(e) => setDpi(parseInt(e.target.value))}
                style={{
                  width: '100%',
                  background: 'var(--bg-primary)',
                  color: '#fff',
                  border: '1px solid var(--border-color)',
                  borderRadius: '6px',
                  padding: '0.4rem',
                  fontSize: '0.8rem',
                  marginTop: '0.2rem',
                }}
              >
                <option value={300}>300 DPI</option>
                <option value={600}>600 DPI (Chuẩn)</option>
              </select>
            </div>

            <div>
              <label style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>YOLO Conf: {conf}</label>
              <input
                type="range"
                min="0.05"
                max="0.8"
                step="0.05"
                value={conf}
                onChange={(e) => setConf(parseFloat(e.target.value))}
                style={{ width: '100%', marginTop: '0.5rem' }}
              />
            </div>

            <div>
              <label style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Tile Size (YOLO):</label>
              <select
                value={tileSize}
                onChange={(e) => setTileSize(parseInt(e.target.value))}
                style={{
                  width: '100%',
                  background: 'var(--bg-primary)',
                  color: '#fff',
                  border: '1px solid var(--border-color)',
                  borderRadius: '6px',
                  padding: '0.4rem',
                  fontSize: '0.8rem',
                  marginTop: '0.2rem',
                }}
              >
                <option value={1024}>1024 x 1024 (Chuẩn)</option>
                <option value={1280}>1280 x 1280</option>
              </select>
            </div>

            <div>
              <label style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Thiết bị tính toán:</label>
              <select
                value={device}
                onChange={(e) => setDevice(e.target.value)}
                style={{
                  width: '100%',
                  background: 'var(--bg-primary)',
                  color: '#fff',
                  border: '1px solid var(--border-color)',
                  borderRadius: '6px',
                  padding: '0.4rem',
                  fontSize: '0.8rem',
                  marginTop: '0.2rem',
                }}
              >
                <option value="auto">Auto (CUDA/CPU)</option>
                <option value="cuda">NVIDIA GPU (CUDA)</option>
                <option value="cpu">CPU Only</option>
              </select>
            </div>
          </div>

          {/* Run Button */}
          <button
            className="btn btn-primary"
            style={{ width: '100%', marginTop: '1.25rem', padding: '0.75rem' }}
            disabled={isUploading || isProcessing || (!file && !currentDrawing)}
            onClick={handleUploadAndRun}
          >
            <Play size={18} />
            {isProcessing ? 'Đang chạy Pipeline AI...' : 'Bắt đầu Số Hóa (Run AI Pipeline)'}
          </button>
        </div>

        {/* Realtime Progress Card (SSE) */}
        {isProcessing && (
          <div className="card" style={{ borderColor: 'var(--accent-cyan)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
              <span style={{ fontSize: '0.85rem', fontWeight: '600', color: 'var(--accent-cyan)' }}>
                {progressInfo?.stage || 'Đang xử lý...'}
              </span>
              <span style={{ fontSize: '0.85rem', fontWeight: '700', color: '#fff' }}>
                {progressInfo?.progress || 0}%
              </span>
            </div>

            {/* Progress bar */}
            <div style={{
              width: '100%',
              height: '8px',
              borderRadius: '4px',
              background: 'var(--bg-primary)',
              overflow: 'hidden',
            }}>
              <div style={{
                width: `${progressInfo?.progress || 5}%`,
                height: '100%',
                background: 'linear-gradient(90deg, var(--accent-cyan), var(--accent-blue))',
                borderRadius: '4px',
                transition: 'width 0.4s ease',
              }} />
            </div>

            <div style={{ marginTop: '0.75rem', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
              Job ID: <code style={{ color: 'var(--accent-cyan)' }}>{progressInfo?.job_id}</code>
            </div>
          </div>
        )}
      </div>

      {/* Right Column: Original Drawing Viewer */}
      <div className="card" style={{ padding: '0.5rem', display: 'flex', flexDirection: 'column' }}>
        <div style={{
          padding: '0.5rem 0.75rem',
          borderBottom: '1px solid var(--border-color)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}>
          <span style={{ fontSize: '0.85rem', fontWeight: '600', color: 'var(--text-primary)' }}>
            Xem trước Bản vẽ gốc ({currentDrawing?.width || 0} x {currentDrawing?.height || 0} px)
          </span>
          <span className="badge" style={{ background: 'rgba(56, 189, 248, 0.1)', color: 'var(--accent-cyan)' }}>
            Trạng thái: {currentDrawing?.status || 'Chưa chọn'}
          </span>
        </div>

        <div style={{ flex: 1, minHeight: 0 }}>
          <DrawingViewer
            drawing={currentDrawing}
            showSymbols={false}
            showOcr={false}
            showLines={false}
          />
        </div>
      </div>
    </div>
  );
}
