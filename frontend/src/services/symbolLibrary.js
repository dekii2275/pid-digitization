const base = `${import.meta.env.VITE_API_BASE_URL || '/api/v1'}/symbol-library`;

async function read(response) {
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(result.detail || 'Không thể xử lý thư viện symbol.');
  return result;
}

export const getSymbolLibrary = () => fetch(base).then(read);

export function importSymbol({ code, name, category, source }) {
  const form = new FormData();
  form.append('code', code);
  form.append('name', name);
  form.append('category', category);
  form.append('source', source);
  return fetch(`${base}/import`, { method: 'POST', body: form }).then(read);
}

export function updateSymbolDefinition(code, changes) {
  return fetch(`${base}/${encodeURIComponent(code)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(changes),
  }).then(read);
}

export function deleteSymbolDefinition(code) {
  return fetch(`${base}/${encodeURIComponent(code)}`, { method: 'DELETE' }).then(read);
}
