const base = import.meta.env?.VITE_API_BASE_URL || '/api/v1';

const fieldLabels = {
  project: 'Dự án / nhà máy',
  area: 'Khu vực',
  tag: 'Tag thiết bị',
  name: 'Tên thiết bị',
  equipment_type: 'Loại thiết bị',
  notes: 'Ghi chú',
  version: 'Phiên bản hồ sơ',
};

function validationMessage(detail) {
  const path = detail.loc || [];
  const field = path.at(-1);
  const label =
    path.includes('occurrence') && field === 'tag'
      ? 'Tag tại vị trí trên bản vẽ'
      : fieldLabels[field] || 'Dữ liệu';
  if (detail.type === 'string_too_short' || detail.type === 'missing') {
    return `${label}: không được để trống.`;
  }
  if (detail.type === 'string_too_long') {
    return `${label}: tối đa ${detail.ctx?.max_length} ký tự.`;
  }
  return `${label}: ${detail.msg || 'giá trị không hợp lệ.'}`;
}

async function request(path, options) {
  const response = await fetch(`${base}${path}`, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail =
      typeof data.detail === 'string'
        ? data.detail
        : Array.isArray(data.detail)
          ? data.detail.map(validationMessage).join(' ')
          : null;
    const error = new Error(
      detail || `Không thể xử lý hồ sơ thiết bị (HTTP ${response.status}). Vui lòng thử lại.`,
    );
    error.status = response.status;
    throw error;
  }
  return data;
}

const json = (method, body) => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});
export const occurrenceRef = ({
  drawing_id,
  page_number,
  source,
  kind,
  item_id,
  generation,
  tag,
  symbol_code = '',
}) => ({ drawing_id, page_number, source, kind, item_id, generation, tag, symbol_code });

export function occurrenceLinkIssue(occurrence, project = occurrence?.project) {
  if (!occurrence) return 'Chọn một vị trí trên bản vẽ để liên kết.';
  if (!occurrence.tag?.trim() && (occurrence.kind !== 'symbol' || !occurrence.symbol_code)) {
    return 'Chọn một symbol có mã loại hoặc một vị trí có tag để liên kết.';
  }
  if (!project?.trim()) {
    return 'Nhập dự án / nhà máy cho hồ sơ để lưu liên kết.';
  }
  const normalize = (value) => (value || '').trim().replace(/\s+/g, ' ').toLowerCase();
  if (occurrence.project?.trim() && normalize(project) !== normalize(occurrence.project)) {
    return 'Dự án của hồ sơ phải trùng dự án bản vẽ để liên kết. Sửa dự án hoặc bỏ chọn liên kết để tạo hồ sơ độc lập.';
  }
  return '';
}

export function assetCreatePayload(fields, occurrence, linkDrawing) {
  if (!linkDrawing) return { ...fields };
  const issue = occurrenceLinkIssue(occurrence, fields.project);
  if (issue) throw new Error(issue);
  return { ...fields, occurrence: occurrenceRef(occurrence) };
}
export const searchTags = (params, signal) =>
  request(`/asset-search?${new URLSearchParams(params)}`, { signal });
export const listAssets = (params, signal) =>
  request(`/assets?${new URLSearchParams(params)}`, { signal });
export const getAsset = (id, signal) => request(`/assets/${id}`, { signal });
export const createAsset = (data) => request('/assets', json('POST', data));
export const updateAsset = (id, data) => request(`/assets/${id}`, json('PUT', data));
export const linkOccurrence = (id, occurrence) =>
  request(`/assets/${id}/occurrences`, json('POST', occurrenceRef(occurrence)));
export const unlinkOccurrence = (id, linkId) =>
  request(`/assets/${id}/occurrences/${linkId}`, { method: 'DELETE' });
export const addDocumentLink = (id, data) =>
  request(`/assets/${id}/documents/links`, json('POST', data));
export const deleteAssetDocument = (id, documentId) =>
  request(`/assets/${id}/documents/${documentId}`, { method: 'DELETE' });
export const assetDocumentUrl = (id, documentId) =>
  `${base}/assets/${id}/documents/${documentId}/download`;
export function uploadAssetDocument(id, file, metadata) {
  const body = new FormData();
  body.append('file', file);
  body.append('title', metadata.title);
  body.append('category', metadata.category);
  return request(`/assets/${id}/documents/upload`, { method: 'POST', body });
}
