const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || '/api/v1';

export async function uploadDrawingDocument(file, { onProgress } = {}) {
  const formData = new FormData();
  formData.append('file', file);
  if (onProgress) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open('POST', `${apiBaseUrl}/documents/upload`);
      xhr.timeout = 15 * 60 * 1000;
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) onProgress(Math.round((event.loaded / event.total) * 100));
      };
      xhr.onload = () => {
        let payload;
        try {
          payload = JSON.parse(xhr.responseText);
        } catch {
          reject(new Error('Máy chủ trả về dữ liệu không hợp lệ. Vui lòng thử lại.'));
          return;
        }
        if (xhr.status >= 200 && xhr.status < 300) resolve(payload);
        else
          reject(
            new Error(
              typeof payload.detail === 'string' ? payload.detail : 'Không thể tải bản vẽ lên.',
            ),
          );
      };
      xhr.onerror = () => reject(new Error('Mất kết nối khi tải file. Vui lòng thử lại.'));
      xhr.ontimeout = () => reject(new Error('Hết thời gian chờ tải file. Vui lòng thử lại.'));
      xhr.onabort = () => reject(new Error('Đã hủy tải file.'));
      xhr.send(formData);
    });
  }
  const response = await fetch(`${apiBaseUrl}/documents/upload`, {
    method: 'POST',
    body: formData,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || 'Không thể tải bản vẽ lên.');
  return payload;
}

async function getJson(path, options) {
  const response = await fetch(`${apiBaseUrl}${path}`, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok)
    throw new Error(
      typeof payload.detail === 'string' ? payload.detail : 'Không thể xử lý yêu cầu.',
    );
  return payload;
}

export function deleteDrawingDocument(drawingId) {
  return getJson(`/documents/${encodeURIComponent(drawingId)}`, { method: 'DELETE' });
}

export function organizeDrawingDocument(id, data) {
  return getJson(`/documents/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
}

export function savePageStatus(id, page, workflow, status) {
  return getJson(`/documents/${encodeURIComponent(id)}/pages/${page}/status`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      status,
      revision: workflow.revision || 0,
      annotation_revision: workflow.annotation_revision || 0,
    }),
  });
}

export const pageThumbnailUrl = (id, page) =>
  `${apiBaseUrl}/documents/${encodeURIComponent(id)}/pages/${page}/thumbnail.jpg`;

export function runAllPipeline(drawingId, page = 1) {
  return getJson(`/documents/${drawingId}/run-all?page_number=${page}`, { method: 'POST' });
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

export function getPageReviewScene(id, page, origin = 'latest') {
  return getJson(
    `/documents/${encodeURIComponent(id)}/pages/${page}/review-scene?origin=${origin}`,
  );
}

export function savePageReviewScene(id, page, data) {
  return getJson(`/documents/${encodeURIComponent(id)}/pages/${page}/review-scene`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
}

export async function downloadPageDxf(id, page, version, name) {
  const response = await fetch(
    `${apiBaseUrl}/documents/${encodeURIComponent(id)}/pages/${page}/review-scene/export.dxf?version=${version}`,
  );
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(typeof data.detail === 'string' ? data.detail : 'Không thể xuất DXF.');
  }
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a');
  link.href = url;
  link.download = `${(name || 'pid').replace(/\.[^.]+$/, '')}-p${page}-v${version}.dxf`;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
