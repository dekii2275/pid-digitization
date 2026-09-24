/**
 * API service for communicating with FastAPI Backend (port 18181).
 */

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:18181/api/v1';
const configuredServerHost = import.meta.env.VITE_SERVER_HOST;
const SERVER_HOST = configuredServerHost === '__SAME_ORIGIN__'
  ? window.location.origin
  : configuredServerHost || 'http://localhost:18181';

export const api = {
  // Projects
  async getProjects() {
    const res = await fetch(`${API_BASE_URL}/projects`);
    if (!res.ok) throw new Error('Failed to fetch projects');
    return res.json();
  },

  // Drawings
  async getDrawings() {
    const res = await fetch(`${API_BASE_URL}/drawings`);
    if (!res.ok) throw new Error('Failed to fetch drawings');
    return res.json();
  },

  async getDrawing(id) {
    const res = await fetch(`${API_BASE_URL}/drawings/${id}`);
    if (!res.ok) throw new Error('Failed to fetch drawing');
    return res.json();
  },

  async uploadDrawing(file, name = '') {
    const formData = new FormData();
    formData.append('file', file);
    if (name) formData.append('name', name);

    const res = await fetch(`${API_BASE_URL}/drawings/upload`, {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) throw new Error('Failed to upload drawing');
    return res.json();
  },

  // Processing & Jobs
  async startProcessing(drawingId) {
    const res = await fetch(`${API_BASE_URL}/drawings/${drawingId}/process`, {
      method: 'POST',
    });
    if (!res.ok) throw new Error('Failed to start processing job');
    return res.json();
  },

  async getJobStatus(jobId) {
    const res = await fetch(`${API_BASE_URL}/jobs/${jobId}`);
    if (!res.ok) throw new Error('Failed to fetch job status');
    return res.json();
  },

  getJobEventsUrl(jobId) {
    return `${API_BASE_URL}/jobs/${jobId}/events`;
  },

  // Symbols (Object Detection)
  async getSymbols(drawingId, minConfidence = 0.0) {
    const res = await fetch(`${API_BASE_URL}/drawings/${drawingId}/symbols?min_confidence=${minConfidence}`);
    if (!res.ok) throw new Error('Failed to fetch symbols');
    return res.json();
  },

  async updateSymbol(symbolId, data) {
    const res = await fetch(`${API_BASE_URL}/symbols/${symbolId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error('Failed to update symbol');
    return res.json();
  },

  async deleteSymbol(symbolId) {
    const res = await fetch(`${API_BASE_URL}/symbols/${symbolId}`, {
      method: 'DELETE',
    });
    if (!res.ok) throw new Error('Failed to delete symbol');
    return res.json();
  },

  // OCR Texts
  async getOcrTexts(drawingId, search = '') {
    const url = new URL(`${API_BASE_URL}/drawings/${drawingId}/ocr`);
    if (search) url.searchParams.append('search', search);
    const res = await fetch(url.toString());
    if (!res.ok) throw new Error('Failed to fetch OCR texts');
    return res.json();
  },

  // Lines
  async getLines(drawingId) {
    const res = await fetch(`${API_BASE_URL}/drawings/${drawingId}/lines`);
    if (!res.ok) throw new Error('Failed to fetch lines');
    return res.json();
  },

  // Topology
  async getTopology(drawingId) {
    const res = await fetch(`${API_BASE_URL}/drawings/${drawingId}/topology`);
    if (!res.ok) throw new Error('Failed to fetch topology');
    return res.json();
  },

  // Tag Search
  async searchTag(drawingId, tag) {
    const res = await fetch(`${API_BASE_URL}/search?drawing_id=${drawingId}&tag=${encodeURIComponent(tag)}`);
    if (!res.ok) throw new Error('Tag not found');
    return res.json();
  },

  // Exports
  async getStructuredJson(drawingId) {
    const res = await fetch(`${API_BASE_URL}/drawings/${drawingId}/exports/json`);
    if (!res.ok) throw new Error('Failed to fetch structured JSON');
    return res.json();
  },

  getDexpiXmlUrl(drawingId) {
    return `${API_BASE_URL}/drawings/${drawingId}/exports/dexpi`;
  },

  // Helper to get static file URL (e.g. uploaded images or debug overlays)
  getImageUrl(filePath) {
    if (!filePath) return '';
    if (filePath.startsWith('http://') || filePath.startsWith('https://')) return filePath;
    // Normalize path separators
    const normalized = filePath.replace(/\\/g, '/');
    if (normalized.includes('/uploads/')) {
      const sub = normalized.split('/uploads/')[1];
      return `${SERVER_HOST}/uploads/${sub}`;
    }
    if (normalized.includes('/artifacts/')) {
      const sub = normalized.split('/artifacts/')[1];
      return `${SERVER_HOST}/artifacts/${sub}`;
    }
    return `${SERVER_HOST}/${normalized}`;
  },
};
