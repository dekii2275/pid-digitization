const base = import.meta.env.VITE_API_BASE_URL || '/api/v1';

async function request(path, options) {
  const response = await fetch(`${base}${path}`, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(
      typeof data.detail === 'string' ? data.detail : 'Không thể xử lý dữ liệu gán nhãn.',
    );
    error.status = response.status;
    throw error;
  }
  return data;
}

export const getDocuments = () => request('/documents');
export const getDocument = (id) => request(`/documents/${encodeURIComponent(id)}`);
export const getDocumentPage = (id, page) =>
  request(`/documents/${encodeURIComponent(id)}/pages/${page}`);
export const getAnnotations = (id, page) =>
  request(`/documents/${encodeURIComponent(id)}/pages/${page}/annotations`);
export const saveAnnotations = (id, page, data) =>
  request(`/documents/${encodeURIComponent(id)}/pages/${page}/annotations`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      revision: data.revision,
      symbols: data.symbols.map(({ id: boxId, label_id, x, y, width, height }) => ({
        id: boxId,
        label_id,
        x,
        y,
        width,
        height,
      })),
      texts: data.texts.map(({ id: boxId, text, x, y, width, height }) => ({
        id: boxId,
        text,
        x,
        y,
        width,
        height,
      })),
      relations: data.relations,
    }),
  });

export async function exportDataset(id, page) {
  const response = await fetch(
    `${base}/documents/${encodeURIComponent(id)}/pages/${page}/annotations/export`,
  );
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || 'Không thể xuất dữ liệu.');
  }
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a');
  link.href = url;
  link.download = `${id}-p${page}-dataset.zip`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
