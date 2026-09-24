import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Navbar } from './components/Navbar';
import { Stepper } from './components/Stepper';
import { Step1Input } from './components/Step1Input';
import { Step2Detection } from './components/Step2Detection';
import { Step3Ocr } from './components/Step3Ocr';
import { api } from './services/api';
import { Share2, FileCode2 } from 'lucide-react';

export default function App() {
  const [currentDrawing, setCurrentDrawing] = useState(null);
  const [activeStep, setActiveStep] = useState(1);

  // Pipeline Data States
  const [symbols, setSymbols] = useState([]);
  const [ocrTexts, setOcrTexts] = useState([]);
  const [, setLines] = useState([]);
  const [topology, setTopology] = useState(null);

  // Processing & SSE Job States
  const [isProcessing, setIsProcessing] = useState(false);
  const [progressInfo, setProgressInfo] = useState({ progress: 0, stage: '', status: '', message: '' });
  const [activeJobId, setActiveJobId] = useState(null);
  const activeDrawingIdRef = useRef(null);

  const clearPipelineData = useCallback(() => {
    setSymbols([]);
    setOcrTexts([]);
    setLines([]);
    setTopology(null);
  }, []);

  // Fetch all drawing-related data
  const loadDrawingData = useCallback(async (drawingId) => {
    if (!drawingId) return;
    activeDrawingIdRef.current = drawingId;
    clearPipelineData();
    try {
      const [symbolsData, ocrData, linesData, topoData] = await Promise.allSettled([
        api.getSymbols(drawingId),
        api.getOcrTexts(drawingId),
        api.getLines(drawingId),
        api.getTopology(drawingId),
      ]);

      if (activeDrawingIdRef.current !== drawingId) return;

      setSymbols(symbolsData.status === 'fulfilled' ? symbolsData.value : []);
      setOcrTexts(ocrData.status === 'fulfilled' ? ocrData.value : []);
      setLines(linesData.status === 'fulfilled' ? linesData.value : []);
      setTopology(topoData.status === 'fulfilled' ? topoData.value : null);
    } catch (err) {
      console.error('Lỗi khi tải dữ liệu bản vẽ:', err);
    }
  }, [clearPipelineData]);

  // Handle drawing selection
  const handleSelectDrawing = (drawing) => {
    setCurrentDrawing(drawing);
    activeDrawingIdRef.current = drawing.id;
    loadDrawingData(drawing.id);
  };

  // Handle new drawing upload start
  const handleNewDrawing = () => {
    setCurrentDrawing(null);
    activeDrawingIdRef.current = null;
    clearPipelineData();
    setActiveStep(1);
    setProgressInfo({ progress: 0, stage: '', status: '', message: '' });
  };

  // Handle drawing created
  const handleDrawingCreated = (drawing) => {
    setCurrentDrawing(drawing);
    activeDrawingIdRef.current = drawing.id;
    clearPipelineData();
    setActiveStep(1);
  };

  // Handle processing started
  const _legacyProcessingStarted = (jobId, _drawingId) => {
    setActiveJobId(jobId);
    setIsProcessing(true);
    setProgressInfo({ percent: 0, status: 'QUEUED', message: 'Hệ thống đã nhận lệnh và bắt đầu xử lý...' });
  };

  const handleProcessingStarted = (jobId, _drawingId) => {
    setActiveJobId(jobId);
    setIsProcessing(true);
    setProgressInfo({ progress: 0, stage: 'QUEUED', status: 'QUEUED', message: 'Pipeline job queued.' });
  };

  // SSE Subscription for real-time progress updates
  useEffect(() => {
    if (!activeJobId || !isProcessing) return;

    const eventUrl = api.getJobEventsUrl(activeJobId);
    const es = new EventSource(eventUrl);

    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        setProgressInfo({
          percent: data.percent || 0,
          status: data.status || '',
          message: data.message || '',
        });

        if (data.status === 'COMPLETED') {
          setIsProcessing(false);
          es.close();
          if (currentDrawing?.id) {
            loadDrawingData(currentDrawing.id);
          }
          setActiveStep(2);
        } else if (data.status === 'FAILED') {
          setIsProcessing(false);
          es.close();
          alert('Quá trình xử lý thất bại: ' + (data.message || 'Lỗi không xác định'));
        }
      } catch (err) {
        console.warn('Lỗi đọc SSE event:', err);
      }
    };

    const handleProgress = (event) => {
      try {
        const data = JSON.parse(event.data);
        setProgressInfo({
          progress: data.progress || 0,
          stage: data.stage || '',
          status: data.status || '',
          message: data.error_message || data.message || '',
        });

        if (data.status === 'COMPLETED') {
          setIsProcessing(false);
          es.close();
          if (currentDrawing?.id) loadDrawingData(currentDrawing.id);
        } else if (data.status === 'FAILED') {
          setIsProcessing(false);
          es.close();
          alert('Pipeline failed: ' + (data.error_message || data.message || 'Unknown error'));
        }
      } catch (err) {
        console.warn('Unable to parse pipeline progress event:', err);
      }
    };

    // The backend emits a named SSE event: `progress`.
    es.addEventListener('progress', handleProgress);

    es.onerror = (err) => {
      console.warn('SSE connection error:', err);
    };

    return () => {
      es.removeEventListener('progress', handleProgress);
      es.close();
    };
  }, [activeJobId, isProcessing, currentDrawing?.id, loadDrawingData]);

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', background: 'var(--bg-primary)' }}>
      {/* Top Navigation Bar */}
      <Navbar
        currentDrawing={currentDrawing}
        onSelectDrawing={handleSelectDrawing}
        onNewDrawing={handleNewDrawing}
      />

      {/* 5-Step Pipeline Stepper */}
      <Stepper
        activeStep={activeStep}
        onStepChange={setActiveStep}
        counts={{
          symbols: symbols.length,
          ocr: ocrTexts.length,
          relationships: topology?.relation_table?.length || 0,
        }}
      />

      {/* Main Content Area */}
      <main style={{ flex: 1, padding: '1rem', overflow: 'hidden' }}>
        {activeStep === 1 && (
          <Step1Input
            currentDrawing={currentDrawing}
            onDrawingCreated={handleDrawingCreated}
            onProcessingStarted={handleProcessingStarted}
            isProcessing={isProcessing}
            progressInfo={progressInfo}
          />
        )}

        {activeStep === 2 && (
          <Step2Detection
            currentDrawing={currentDrawing}
            symbols={symbols}
            onSymbolsUpdated={() => currentDrawing && loadDrawingData(currentDrawing.id)}
          />
        )}

        {activeStep === 3 && (
          <Step3Ocr
            currentDrawing={currentDrawing}
            ocrTexts={ocrTexts}
            onOcrUpdated={() => currentDrawing && loadDrawingData(currentDrawing.id)}
          />
        )}

        {activeStep === 4 && (
          <div style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            height: 'calc(100vh - 140px)',
            background: 'var(--bg-secondary)',
            borderRadius: '0.75rem',
            border: '1px solid var(--border-color)',
            textAlign: 'center',
            padding: '2rem',
          }}>
            <div style={{
              width: '64px',
              height: '64px',
              borderRadius: '50%',
              background: 'rgba(56, 189, 248, 0.1)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              marginBottom: '1.25rem',
              color: 'var(--accent-cyan)',
            }}>
              <Share2 size={32} />
            </div>
            <h2 style={{ fontSize: '1.5rem', fontWeight: 600, marginBottom: '0.5rem' }}>
              Bước 4: Hiểu quan hệ (Topology & Network Graph)
            </h2>
            <p style={{ color: 'var(--text-secondary)', maxWidth: '540px', marginBottom: '1.5rem', lineHeight: 1.6 }}>
              Hiển thị biểu đồ kết nối thiết bị & đường ống tương tác thông qua Cytoscape.js cùng bảng trích xuất quan hệ kết nối (From, Relation, To, Line/Tag).
            </p>
            <div style={{
              padding: '0.75rem 1.25rem',
              borderRadius: '0.5rem',
              background: 'var(--bg-card)',
              border: '1px solid var(--border-color)',
              display: 'flex',
              alignItems: 'center',
              gap: '0.75rem',
              color: 'var(--text-secondary)',
              fontSize: '0.875rem',
            }}>
              <span>Đang sẵn sàng cho Milestone M4</span>
            </div>
          </div>
        )}

        {activeStep === 5 && (
          <div style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            height: 'calc(100vh - 140px)',
            background: 'var(--bg-secondary)',
            borderRadius: '0.75rem',
            border: '1px solid var(--border-color)',
            textAlign: 'center',
            padding: '2rem',
          }}>
            <div style={{
              width: '64px',
              height: '64px',
              borderRadius: '50%',
              background: 'rgba(16, 185, 129, 0.1)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              marginBottom: '1.25rem',
              color: 'var(--accent-green)',
            }}>
              <FileCode2 size={32} />
            </div>
            <h2 style={{ fontSize: '1.5rem', fontWeight: 600, marginBottom: '0.5rem' }}>
              Bước 5: Sản phẩm đầu ra (Structured JSON, DEXPI XML & Tra cứu)
            </h2>
            <p style={{ color: 'var(--text-secondary)', maxWidth: '540px', marginBottom: '1.5rem', lineHeight: 1.6 }}>
              Xuất dữ liệu P&ID số hóa sang định dạng chuẩn công nghiệp DEXPI XML, JSON cấu trúc phân cấp và công cụ tra cứu tag trực tiếp (như T-101, P-101A).
            </p>
            <div style={{
              padding: '0.75rem 1.25rem',
              borderRadius: '0.5rem',
              background: 'var(--bg-card)',
              border: '1px solid var(--border-color)',
              display: 'flex',
              alignItems: 'center',
              gap: '0.75rem',
              color: 'var(--text-secondary)',
              fontSize: '0.875rem',
            }}>
              <span>Đang sẵn sàng cho Milestone M7 & M8</span>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
