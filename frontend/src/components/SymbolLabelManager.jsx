import { useEffect, useMemo, useState } from 'react';
import { ListFilter, Search, Trash2, Upload } from 'lucide-react';
import SymbolPreview from './SymbolPreview';
import { deleteSymbolDefinition, getSymbolLibrary, importSymbol, updateSymbolDefinition } from '../services/symbolLibrary';

export default function SymbolLabelManager() {
  const [symbols, setSymbols] = useState([]);
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('All');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(null);
  const [draft, setDraft] = useState({ name: '', category: '' });

  const reload = async () => {
    try { setSymbols(await getSymbolLibrary()); setError(''); }
    catch (cause) { setError(cause.message); }
  };
  useEffect(() => {
    getSymbolLibrary().then(setSymbols).catch((cause) => setError(cause.message));
  }, []);

  const categories = useMemo(() => ['All', ...new Set(symbols.map((item) => item.category))], [symbols]);
  const visible = useMemo(() => symbols.filter((item) => (
    (category === 'All' || item.category === category)
    && `${item.code} ${item.name}`.toLowerCase().includes(query.trim().toLowerCase())
  )), [symbols, category, query]);
  const enabledCount = symbols.filter((item) => item.enabled).length;

  const submitImport = async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    setBusy(true); setError(''); setMessage('');
    try {
      const created = await importSymbol({
        code: data.get('code'), name: data.get('name'), category: data.get('category'),
        source: data.get('source'), preview: data.get('preview'),
      });
      form.reset();
      setMessage(`Đã lưu ${created.code} vào kho symbol.`);
      await reload();
    } catch (cause) { setError(cause.message); }
    finally { setBusy(false); }
  };

  const update = async (code, changes) => {
    setBusy(true); setError(''); setMessage('');
    try {
      const saved = await updateSymbolDefinition(code, changes);
      setSymbols((items) => items.map((item) => item.code === code ? saved : item));
      setEditing(null);
    } catch (cause) { setError(cause.message); }
    finally { setBusy(false); }
  };

  const remove = async (item) => {
    if (!window.confirm(`Xóa ${item.code} - ${item.name} khỏi thư viện? Bản vẽ đã lưu vẫn giữ nguyên.`)) return;
    setBusy(true); setError(''); setMessage('');
    try {
      await deleteSymbolDefinition(item.code);
      setSymbols((items) => items.filter((symbol) => symbol.code !== item.code));
      setEditing(null);
      setMessage(`Đã xóa ${item.code} khỏi thư viện.`);
    } catch (cause) { setError(cause.message); }
    finally { setBusy(false); }
  };

  return <main className="symbol-label-manager">
    <section className="label-manager-header">
      <div><p>THƯ VIỆN SYMBOL</p><h2>Quản lý symbol chuẩn</h2><span>Dữ liệu được lưu trên máy chủ. Hai symbol từ <code>PPID_SYMBOL</code> là dữ liệu khởi đầu.</span></div>
      <div className="label-manager-summary"><b>{enabledCount}</b><span>/ {symbols.length} đang bật</span></div>
    </section>

    <form className="symbol-import" onSubmit={submitImport}>
      <div><b>Import symbol</b><small>Mỗi lần nhập một symbol. File gốc và ảnh xem trước được lưu riêng.</small></div>
      <label>Mã symbol<input name="code" maxLength="64" placeholder="VD: VLV-003" required /></label>
      <label>Tên symbol<input name="name" maxLength="255" placeholder="Tên đã kiểm tra" required /></label>
      <label>Nhóm<input name="category" maxLength="100" defaultValue="Valves" required /></label>
      <label>File gốc<input name="source" type="file" accept=".dwg,.dxf,.png,.jpg,.jpeg,.webp,.bmp,.tif,.tiff,.pdf" required /></label>
      <label>Ảnh xem trước<input name="preview" type="file" accept=".png,.jpg,.jpeg,.webp" required /></label>
      <button type="submit" disabled={busy}><Upload size={14} /> {busy ? 'Đang lưu…' : 'Import vào kho'}</button>
    </form>
    {error && <p className="symbol-library-error" role="alert">{error}</p>}
    {message && <p className="symbol-library-message" role="status">{message}</p>}

    <section className="label-manager-controls" aria-label="Lọc symbol">
      <label className="label-search"><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Tìm mã hoặc tên symbol" /></label>
      <label className="label-filter"><ListFilter size={15} /><select value={category} onChange={(event) => setCategory(event.target.value)}>{categories.map((item) => <option key={item}>{item}</option>)}</select></label>
    </section>
    <section className="label-table-wrap"><table className="symbol-label-table"><thead><tr><th>Symbol</th><th>Tên và nguồn</th><th>Trạng thái</th></tr></thead><tbody>
      {visible.map((item) => <tr key={item.code} className={item.enabled ? '' : 'is-disabled'}>
        <td><div className="symbol-cell"><SymbolPreview symbol={item} /><code>{item.code}</code></div></td>
        <td>{editing === item.code ? <form className="symbol-inline-edit" onSubmit={(event) => { event.preventDefault(); update(item.code, draft); }}>
          <input value={draft.name} onChange={(event) => setDraft((old) => ({ ...old, name: event.target.value }))} required />
          <input value={draft.category} onChange={(event) => setDraft((old) => ({ ...old, category: event.target.value }))} required />
          <button disabled={busy}>Lưu</button><button type="button" onClick={() => setEditing(null)}>Hủy</button>
        </form> : <div className="symbol-name"><strong>{item.name}</strong><small>{item.category} · {item.origin} · <a href={item.source_url}>Tải file gốc</a></small><button type="button" className="edit-label-button" onClick={() => { setEditing(item.code); setDraft({ name: item.name, category: item.category }); }}>Chỉnh sửa</button></div>}</td>
        <td><div className="symbol-row-actions"><button type="button" disabled={busy} className={`status-toggle ${item.enabled ? 'is-on' : ''}`} aria-pressed={item.enabled} onClick={() => update(item.code, { enabled: !item.enabled })}><i /><span>{item.enabled ? 'Bật' : 'Tắt'}</span></button><button type="button" disabled={busy} className="symbol-delete" onClick={() => remove(item)} title={`Xóa ${item.code}`}><Trash2 size={13} /> Xóa</button></div></td>
      </tr>)}
      {visible.length === 0 && <tr><td className="label-empty" colSpan="3">Chưa có symbol phù hợp.</td></tr>}
    </tbody></table></section>
  </main>;
}
