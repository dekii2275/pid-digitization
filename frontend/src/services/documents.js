const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || '/api/v1';

export async function uploadDrawingDocument(file) {
  const formData = new FormData();
  formData.append('file', file);
  const response = await fetch(`${apiBaseUrl}/documents/upload`, { method: 'POST', body: formData });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || 'Không thể tải bản vẽ lên.');
  return payload;
}

async function getJson(path, options) {
  const response = await fetch(`${apiBaseUrl}${path}`, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || 'Không thể gọi pipeline.');
  return payload;
}

export function runAllPipeline(drawingId) {
  return getJson(`/documents/${drawingId}/run-all`, { method: 'POST' });
}

export function getPipelineJob(jobId) {
  return getJson(`/jobs/${jobId}`);
}

export function getPipelineResults(jobId) {
  return getJson(`/jobs/${jobId}/results`);
}

export function getFinalReviewResults(jobId) {
  return getJson(`/jobs/${jobId}/final-results`);
}

export function saveFinalReviewResults(jobId, scene) {
  return getJson(`/jobs/${jobId}/final-results`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(scene),
  });
}
