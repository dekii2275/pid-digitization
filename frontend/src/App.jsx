import { useEffect, useMemo, useRef, useState } from 'react';
import {
  CheckCircle2, Download, FileCode2, FileText, Layers, Maximize2, Minimize2, Play, Scan, Search,
  Share2, Sliders, Type, Upload,
} from 'lucide-react';
import './App.css';
import TiledDrawingCanvas from './components/TiledDrawingCanvas';
import ReviewWorkspace from './components/ReviewWorkspace';
import EditablePidWorkspace, { downloadSceneFile } from './components/EditablePidWorkspace';
import SymbolLabelManager from './components/SymbolLabelManager';
import { getPipelineJob, getPipelineResults, runAllPipeline, saveFinalReviewResults, uploadDrawingDocument } from './services/documents';

const symbols = [
  { id: 'P-101A', type: 'Centrifugal Pump', confidence: 0.96, x: 20, y: 56, w: 11, h: 14, color: '#e67e22' },
  { id: 'V-101', type: 'Gate Valve', confidence: 0.93, x: 43, y: 47, w: 8, h: 11, color: '#0070c0' },
  { id: 'T-101', type: 'Vertical Vessel', confidence: 0.98, x: 66, y: 28, w: 15, h: 27, color: '#c0392b' },
  { id: 'TI-101', type: 'Temperature Indicator', confidence: 0.91, x: 72, y: 69, w: 8, h: 9, color: '#239b56' },
];
const drawings = [];
const ocrRows = ['P-101A', 'V-101', 'T-101', '3”-P-1001-CS'];

// Kept temporarily as a design reference; it is no longer rendered as mock data.
// eslint-disable-next-line no-unused-vars
function Diagram() {
  return <svg className="pid-diagram" viewBox="0 0 1200 760" aria-label="P&ID drawing sample">
    <defs><pattern id="cadGrid" width="28" height="28" patternUnits="userSpaceOnUse"><path d="M 28 0 L 0 0 0 28" fill="none" stroke="#d7e0e8" strokeWidth=".7" /></pattern></defs>
    <rect width="1200" height="760" fill="#fbfdff" /><rect width="1200" height="760" fill="url(#cadGrid)" />
    <g fill="none" stroke="#263746" strokeWidth="5"><path d="M65 474 H260 V375 H470 H590 V243 H820 H1085" /><path d="M820 243 V550 H1100" /><path d="M470 375 V603 H615" strokeDasharray="13 8" /></g>
    <g fill="#fff" stroke="#263746" strokeWidth="4"><circle cx="260" cy="474" r="59" /><path d="M230 474 h60 M260 444 v60" /><path d="M430 341 l40 34 -40 34 -40 -34z" /><rect x="770" y="126" width="100" height="237" rx="10" /><path d="M770 159 h100 M770 330 h100" /><circle cx="820" cy="550" r="31" /></g>
    <g fill="#263746" fontFamily="Arial, sans-serif"><text x="192" y="565" fontSize="24" fontWeight="700">P-101A</text><text x="410" y="320" fontSize="23" fontWeight="700">V-101</text><text x="782" y="397" fontSize="24" fontWeight="700">T-101</text><text x="780" y="610" fontSize="22" fontWeight="700">TI-101</text><text x="485" y="337" fontSize="17">3”-P-1001-CS</text><text x="883" y="230" fontSize="15" fill="#64748b">TK-01</text></g>
    <g fill="#64748b" fontFamily="Arial, sans-serif" fontSize="14"><text x="65" y="448">FEED WATER</text><text x="965" y="214">PROCESS OUT</text><text x="844" y="579">TEMP. SIGNAL</text></g>
    <rect x="932" y="628" width="220" height="90" fill="#fff" stroke="#263746" strokeWidth="1.5" /><text x="946" y="654" fill="#263746" fontFamily="Arial" fontSize="15" fontWeight="700">P&amp;ID - UNIT 100</text><text x="946" y="680" fill="#64748b" fontFamily="Arial" fontSize="12">Drawing: PID-101 · Rev. 01</text><text x="946" y="703" fill="#64748b" fontFamily="Arial" fontSize="12">Status: AI review</text>
  </svg>;
}

function Canvas() {
  return <div className="cad-canvas empty-canvas"><div className="empty-drawing-state"><Upload size={30} /><h2>Chưa có bản vẽ để xem</h2><p>Vui lòng upload tệp P&amp;ID PDF, PNG hoặc JPG để bắt đầu review.</p><span>Sau khi upload, bạn có thể pan, zoom và xem toàn màn hình.</span></div></div>;
}

function RibbonButton({ icon: Icon, label, primary, active, onClick }) {
  return <button
    className={`ribbon-button ${primary ? 'primary' : ''} ${active ? 'is-active' : ''}`}
    onClick={onClick}
    aria-pressed={active}
  ><Icon size={18} /><span>{label}</span></button>;
}

export default function App() {
  const [uploadedDrawing, setUploadedDrawing] = useState(null);
  const [fileName, setFileName] = useState('Chưa có bản vẽ');
  const [activeDrawing, setActiveDrawing] = useState({ id: 'Chưa có bản vẽ', name: 'Chưa có bản vẽ', revision: '—' });
  const [selectedSymbol, setSelectedSymbol] = useState(symbols[0]);
  const [inspectorTab, setInspectorTab] = useState('properties');
  const [ribbonTab, setRibbonTab] = useState('Home');
  const [isRunning, setIsRunning] = useState(false);
  const [progress, setProgress] = useState(0);
  const [pipelineStage, setPipelineStage] = useState('');
  const [aiResults, setAiResults] = useState(null);
  const [completedJobId, setCompletedJobId] = useState(null);
  const [sceneRevision, setSceneRevision] = useState(0);
  const [search, setSearch] = useState('');
  const [showDetections, setShowDetections] = useState(false);
  const [showTags, setShowTags] = useState(false);
  const [showConnections, setShowConnections] = useState(false);
  const [zoom, setZoom] = useState(100);
  const [isUploading, setIsUploading] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [lowConfidenceOnly] = useState(false);
  const [accepted, setAccepted] = useState([]);
  const [editing, setEditing] = useState(false);
  const [tagDraft, setTagDraft] = useState('');
  const [toast, setToast] = useState('');
  const searchRef = useRef(null);
  const drawingViewerRef = useRef(null);
  const drawingWorkspaceRef = useRef(null);
  useEffect(() => {
    const updateFullscreen = () => setIsFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener('fullscreenchange', updateFullscreen);
    return () => document.removeEventListener('fullscreenchange', updateFullscreen);
  }, []);
  const visibleSymbols = useMemo(() => symbols.filter((item) => !lowConfidenceOnly || item.confidence < 0.95), [lowConfidenceOnly]);
  const filteredTags = useMemo(() => ocrRows.filter((tag) => tag.toLowerCase().includes(search.toLowerCase())), [search]);
  const notify = (message) => { setToast(message); window.setTimeout(() => setToast(''), 3600); };
  const chooseFile = async (file) => {
    if (!file || isUploading) return;
    setIsUploading(true);
    notify(`Đang tải ${file.name} lên và tạo preview…`);
    try {
      const uploaded = await uploadDrawingDocument(file);
      setUploadedDrawing(uploaded);
      setFileName(uploaded.name);
      setActiveDrawing({ id: 'LOCAL', name: uploaded.name, revision: 'Local' });
      setAiResults(null);
      setCompletedJobId(null);
      setShowDetections(false);
      setShowTags(false);
      setShowConnections(false);
      notify(`Đã sẵn sàng: ${uploaded.name} · ${uploaded.width} × ${uploaded.height}px · ${uploaded.page_count} trang.`);
    } catch (error) {
      notify(error.message || 'Không thể tải bản vẽ lên.');
    } finally {
      setIsUploading(false);
    }
  };
  const selectDrawing = (drawing) => { setActiveDrawing(drawing); setUploadedDrawing(null); setFileName(`${drawing.id}.png`); notify(`Đã chuyển sang ${drawing.name}.`); };
  const runDemo = async () => {
    if (!uploadedDrawing) { notify('Vui lòng upload bản vẽ trước khi chạy pipeline.'); return; }
    if (isRunning) return;
    setIsRunning(true);
    setProgress(0);
    setPipelineStage('QUEUED');
    setAiResults(null);
    setCompletedJobId(null);
    setShowDetections(false);
    setShowTags(false);
    setShowConnections(false);
    try {
      const created = await runAllPipeline(uploadedDrawing.id);
      let job = created;
      while (job.status === 'QUEUED' || job.status === 'RUNNING') {
        setProgress(job.progress);
        setPipelineStage(job.stage);
        await new Promise((resolve) => window.setTimeout(resolve, 1000));
        job = await getPipelineJob(created.job_id);
      }
      setProgress(job.progress);
      setPipelineStage(job.stage);
      if (job.status !== 'COMPLETED') throw new Error(job.error_message || 'Pipeline xử lý thất bại.');
      const results = await getPipelineResults(created.job_id);
      setAiResults(results);
      setCompletedJobId(created.job_id);
      setSceneRevision(0);
      // Result layers remain off until the reviewer explicitly selects Detect,
      // OCR, or Connect in the AI review ribbon.
      setShowDetections(false);
      setShowTags(false);
      setShowConnections(false);
      setRibbonTab('Editor');
      notify(`Pipeline hoàn tất: ${results.symbols?.length || 0} symbols, ${results.texts?.length || 0} OCR tags, ${results.lines?.length || 0} lines.`);
    } catch (error) {
      notify(error.message || 'Pipeline xử lý thất bại.');
    } finally {
      setIsRunning(false);
    }
  };
  const toggleResultLayer = (layer) => {
    if (!aiResults) {
      notify('Chưa có kết quả AI. Hãy chạy pipeline trước.');
      return;
    }
    const toggles = {
      detections: [showDetections, setShowDetections, 'Detection'],
      tags: [showTags, setShowTags, 'OCR'],
      connections: [showConnections, setShowConnections, 'Connect'],
    };
    const [isVisible, setVisible, label] = toggles[layer];
    setVisible(!isVisible);
    notify(`${isVisible ? 'Đã ẩn' : 'Đang hiển thị'} overlay ${label}.`);
  };
  const downloadFile = (kind) => {
    if (aiResults && uploadedDrawing && (kind === 'JSON' || kind === 'DEXPI')) {
      downloadSceneFile(aiResults, uploadedDrawing, kind === 'JSON' ? 'json' : 'dexpi');
      notify(`Đã xuất file ${kind === 'DEXPI' ? 'DEXPI XML' : 'scene JSON'}.`);
      return;
    }
    const content = kind === 'JSON' ? JSON.stringify({ drawing: activeDrawing.id, symbols, ocr_tags: ocrRows, mode: 'frontend-demo' }, null, 2) : `<?xml version="1.0"?><PlantItem><Drawing id="${activeDrawing.id}"/><Equipment count="4"/><Instrumentation count="1"/></PlantItem>`;
    const type = kind === 'JSON' ? 'application/json' : 'application/xml';
    const extension = kind === 'JSON' ? 'json' : 'xml';
    const url = URL.createObjectURL(new Blob([content], { type }));
    const link = document.createElement('a');
    link.href = url;
    link.download = `${activeDrawing.id}-review.${extension}`;
    link.click();
    URL.revokeObjectURL(url);
    notify(`Đã tạo file ${kind} trên trình duyệt.`);
  };
  const acceptDetection = () => { if (!accepted.includes(selectedSymbol.id)) setAccepted((items) => [...items, selectedSymbol.id]); notify(`Đã accept ${selectedSymbol.id} (mock review state).`); };
  const saveTag = () => { if (!tagDraft.trim()) return; notify(`Đã lưu tag ${tagDraft.trim()} cho ${selectedSymbol.id} (mock).`); setEditing(false); setTagDraft(''); };
  const paletteSelect = (name) => notify(`Đã chọn nhóm symbol “${name}”. API placement sẽ được nối sau.`);
  const newDrawing = () => { setActiveDrawing({ id: 'PID-NEW', name: 'PID-NEW · Untitled', revision: 'Draft' }); setUploadedDrawing(null); setFileName('PID-NEW.png'); notify('Đã tạo bản vẽ mock mới.'); };
  const toggleFullscreen = async () => {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await drawingWorkspaceRef.current?.requestFullscreen();
    } catch {
      notify('Trình duyệt chưa cho phép bật toàn màn hình.');
    }
  };
  return <div className="engineering-app">
    {toast && <div className="toast"><CheckCircle2 size={15} /> {toast}</div>}
    <header className="titlebar"><div className="app-title"><div className="vpi-lockup"><img src="/vpi-logo-green.png" alt="Petrovietnam VPI" /></div><div className="product-title"><strong>VPI P&amp;ID Digitalization</strong><small>Vietnam Petroleum Institute</small></div><em>Project: Unit 100</em></div><div className="drawing-tabs"><button className="drawing-tab active"><FileText size={14} /> {activeDrawing.id}</button><button className="drawing-tab" onClick={newDrawing}>+ New</button></div><div className="title-actions"><span><i /> Local demo</span><button onClick={() => downloadFile('JSON')}><Download size={14} /> Export</button></div></header>
    <section className="ribbon"><div className="ribbon-tabs">{['Home', 'Review', 'Editor', 'Data', 'View', 'Nhãn symbol'].map((tab) => <button key={tab} onClick={() => { setRibbonTab(tab); notify(`Đã chọn ribbon ${tab}.`); }} className={ribbonTab === tab ? 'active' : ''}>{tab}</button>)}</div><div className="ribbon-tools"><div className="tool-group"><RibbonButton icon={Upload} label={isUploading ? 'Uploading…' : 'Open'} onClick={() => !isUploading && document.getElementById('drawing-upload').click()} /><input id="drawing-upload" type="file" accept="image/png,image/jpeg,application/pdf" onChange={(event) => { chooseFile(event.target.files?.[0]); event.target.value = ''; }} /><RibbonButton icon={Play} label={isRunning ? `${progress}%` : 'Run all'} primary onClick={runDemo} /><small>Drawing</small></div><div className="tool-group"><RibbonButton icon={Scan} label="Detect" active={showDetections} onClick={() => toggleResultLayer('detections')} /><RibbonButton icon={Type} label="OCR" active={showTags} onClick={() => toggleResultLayer('tags')} /><RibbonButton icon={Share2} label="Connect" active={showConnections} onClick={() => toggleResultLayer('connections')} /><small>AI review</small></div><div className="tool-group"><RibbonButton icon={Sliders} label={lowConfidenceOnly ? 'All items' : 'Low conf.'} onClick={() => notify(aiResults ? 'Low-confidence filter sẽ được nối vào review queue ở bước tiếp theo.' : 'Chưa có detection để lọc.')} /><RibbonButton icon={Search} label="Find tag" onClick={() => notify(aiResults ? 'OCR tags đã sẵn sàng trong kết quả pipeline.' : 'Chưa có tag/OCR để tìm.')} /><RibbonButton icon={CheckCircle2} label="Validate" onClick={() => notify(aiResults ? 'Kết quả AI đã sẵn sàng để review.' : 'Chưa có kết quả AI để validate.')} /><small>Tools</small></div><div className="tool-group"><RibbonButton icon={FileCode2} label="JSON" onClick={() => downloadFile('JSON')} /><RibbonButton icon={Download} label="DEXPI" onClick={() => downloadFile('DEXPI')} /><small>Output</small></div></div></section>
    {ribbonTab === 'Nhãn symbol' ? <SymbolLabelManager /> : ribbonTab === 'Editor' ? <EditablePidWorkspace key={`${completedJobId || 'empty-editor'}-${sceneRevision}`} drawing={uploadedDrawing} results={aiResults} jobId={completedJobId} onNotify={notify} onSave={async (scene) => {
      const saved = await saveFinalReviewResults(completedJobId, scene);
      setAiResults(saved.result);
      setSceneRevision((value) => value + 1);
      return saved;
    }} /> : ribbonTab === 'Review' ? <ReviewWorkspace key={`${completedJobId || 'empty-review'}-${sceneRevision}`} drawing={uploadedDrawing} results={aiResults} jobId={completedJobId} onZoomChange={setZoom} onSave={async (scene) => {
      const saved = await saveFinalReviewResults(completedJobId, scene);
      setAiResults(saved.result);
      setSceneRevision((value) => value + 1);
      return saved;
    }} /> : <main className="workspace-grid">
      <aside className="project-manager pane"><div className="pane-title"><strong>PROJECT MANAGER</strong><button onClick={() => notify('Project menu mock: import, properties, members.')}>•••</button></div><div className="tree"><div className="tree-root">▼ <b>Unit 100 — Digitalization</b></div><div className="tree-folder">▼ <FileText size={14} /> P&amp;ID Drawings</div>{drawings.map((drawing) => <button key={drawing.id} className={`tree-item ${activeDrawing.id === drawing.id ? 'selected' : ''}`} onClick={() => selectDrawing(drawing)}>▣&nbsp; {drawing.name}</button>)}<div className="tree-folder" onClick={() => notify('Plant 3D Drawings đang ở mock mode.')}>▶ <Layers size={14} /> Plant 3D Drawings</div><div className="tree-folder" onClick={() => notify('Line list sẽ xuất hiện khi nối API.')}>▶ <FileCode2 size={14} /> Line Lists</div><div className="tree-folder" onClick={() => notify('Review set hiện có 1 drawing.')}>▶ <Share2 size={14} /> Review Sets</div></div><div className="project-bottom"><strong>Drawing details</strong><span>Revision: {activeDrawing.revision}</span><span>Status: <b>{accepted.length === symbols.length ? 'REVIEWED' : 'AI REVIEW'}</b></span><span>{accepted.length} / {symbols.length} accepted</span></div></aside>
      <section className="drawing-workspace pane" ref={drawingWorkspaceRef}><div className="canvas-toolbar"><div><span className="drawing-name">{fileName}</span><button onClick={() => uploadedDrawing ? drawingViewerRef.current?.fit() : setZoom(100)} title="Fit drawing">⌖</button><button onClick={() => uploadedDrawing ? drawingViewerRef.current?.zoomOut() : setZoom((value) => Math.max(70, value - 10))}>−</button><span>{zoom}%</span><button onClick={() => uploadedDrawing ? drawingViewerRef.current?.zoomIn() : setZoom((value) => Math.min(160, value + 10))}>+</button><button onClick={() => uploadedDrawing ? drawingViewerRef.current?.fit() : setZoom(130)} title="Zoom selection">⤢</button><button className="fullscreen-button" onClick={toggleFullscreen} title={isFullscreen ? 'Thoát toàn màn hình (Esc)' : 'Xem bản vẽ toàn màn hình'}>{isFullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}</button></div><div><label><input type="checkbox" disabled={!aiResults} checked={showDetections} onChange={(event) => setShowDetections(event.target.checked)} /> Detections</label><label><input type="checkbox" disabled={!aiResults} checked={showTags} onChange={(event) => setShowTags(event.target.checked)} /> Tags</label><label><input type="checkbox" disabled={!aiResults} checked={showConnections} onChange={(event) => setShowConnections(event.target.checked)} /> Connect</label><span className="status-chip">{isUploading ? 'Uploading…' : isRunning ? `${pipelineStage} ${progress}%` : aiResults ? 'AI results loaded' : uploadedDrawing ? 'Viewer ready · waiting AI' : 'Chờ upload'}</span></div></div>{uploadedDrawing ? <TiledDrawingCanvas ref={drawingViewerRef} drawing={uploadedDrawing} results={aiResults} showDetections={showDetections} showTags={showTags} showConnections={showConnections} onZoomChange={setZoom} /> : <Canvas />}</section>
      <aside className="inspector pane"><div className="inspector-tabs"><button className={inspectorTab === 'properties' ? 'active' : ''} onClick={() => setInspectorTab('properties')}>Properties</button><button className={inspectorTab === 'palette' ? 'active' : ''} onClick={() => setInspectorTab('palette')}>Tool Palette</button></div>{inspectorTab === 'properties' ? <div className="property-content"><div className="selected-object"><span style={{ background: selectedSymbol.color }} /><div><small>SELECTED P&amp;ID OBJECT</small><h2>{selectedSymbol.id}</h2><p>{selectedSymbol.type}</p></div>{accepted.includes(selectedSymbol.id) && <CheckCircle2 className="accepted-icon" size={20} />}</div><div className="property-section"><h3>General</h3><dl><dt>Tag</dt><dd>{selectedSymbol.id}</dd><dt>Class</dt><dd>{selectedSymbol.type}</dd><dt>Source</dt><dd><b className="ai-label">AI DETECTED</b></dd><dt>Confidence</dt><dd>{Math.round(selectedSymbol.confidence * 100)}%</dd></dl></div><div className="property-section"><h3>Review</h3><button className="review-ok" onClick={acceptDetection}><CheckCircle2 size={15} /> {accepted.includes(selectedSymbol.id) ? 'Accepted' : 'Accept detection'}</button><button className="review-edit" onClick={() => { setEditing((value) => !value); setTagDraft(selectedSymbol.id); }}>{editing ? 'Cancel editing' : 'Edit properties'}</button>{editing && <div className="edit-form"><input value={tagDraft} onChange={(event) => setTagDraft(event.target.value)} /><button onClick={saveTag}>Save mock</button></div>}</div><div className="property-section tag-search"><h3>OCR &amp; Tag search</h3><label><Search size={14} /><input ref={searchRef} value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search tag" /></label>{filteredTags.map((tag) => <button key={tag} onClick={() => { const found = symbols.find((item) => item.id === tag); if (found) { setSelectedSymbol(found); notify(`Đã focus ${tag}.`); } else notify(`Đã chọn line tag ${tag}.`); }}><Type size={13} /> {tag}</button>)}</div><div className="review-list"><h3>{lowConfidenceOnly ? 'Low confidence queue' : 'Detection queue'}</h3>{visibleSymbols.map((item) => <button key={item.id} onClick={() => setSelectedSymbol(item)}><i style={{ background: item.color }} />{item.id}<span>{Math.round(item.confidence * 100)}%</span></button>)}</div></div> : <div className="palette-content"><p>STANDARD SYMBOLS</p>{['Equipment', 'Pumps', 'Valves', 'Fittings', 'Instruments', 'Line connectors'].map((item, index) => <button key={item} onClick={() => paletteSelect(item)}><span>{['▭', '◉', '◇', '⊣', '◌', '─'][index]}</span>{item}<b>›</b></button>)}<small>Symbol palette is display-only in this frontend demo.</small></div>}</aside>
    </main>}
    <footer className="statusbar"><span>MODEL</span><span>Sheet: 1 / 1</span><span>Coordinates: 1,024.00, 648.00</span><span>Snap: ON</span><span className="right">{toast || 'P&ID digitization · local frontend mode'}</span></footer>
  </div>;
}
