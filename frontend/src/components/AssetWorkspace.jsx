import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Download,
  FileText,
  FolderOpen,
  Plus,
  RefreshCw,
  Search,
  Unlink,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';
import TiledDrawingCanvas from './TiledDrawingCanvas';
import { getDocumentPage, getDocuments } from '../services/annotations';
import {
  addDocumentLink,
  assetCreatePayload,
  assetDocumentUrl,
  createAsset,
  deleteAssetDocument,
  getAsset,
  linkOccurrence,
  listAssets,
  occurrenceLinkIssue,
  searchTags,
  unlinkOccurrence,
  updateAsset,
  uploadAssetDocument,
} from '../services/assets';
import './AssetWorkspace.css';

const categories = {
  datasheet: 'Datasheet',
  manual: 'Hướng dẫn',
  photo: 'Ảnh hiện trường',
  inspection: 'Kiểm định',
  maintenance: 'Bảo trì',
  other: 'Khác',
};
const statuses = {
  saved_review: 'Đã lưu review',
  completed: 'Trang đã hoàn tất',
  pending_review: 'Chờ kiểm tra',
  in_progress: 'Đang làm',
  not_started: 'Chưa kiểm tra',
};
const fields = [
  ['project', 'Dự án / nhà máy', 120, true],
  ['area', 'Khu vực', 120],
  ['tag', 'Tag thiết bị', 120, true],
  ['name', 'Tên thiết bị', 240],
  ['equipment_type', 'Loại thiết bị', 120],
];
const emptyProfile = { project: '', area: '', tag: '', name: '', equipment_type: '', notes: '' };
const sourceKey = (item) =>
  item &&
  [
    item.drawing_id,
    item.page_number,
    item.source,
    item.kind,
    item.item_id,
    item.generation,
    item.tag,
  ].join(':');
const locationLabel = (item) =>
  `${item.drawing_number || item.drawing_name} · Trang ${item.page_number} · Rev. ${item.revision_label || 'chưa khai báo'}`;

function AssetForm({ initial, occurrence, onSaved, onCancel }) {
  const [draft, setDraft] = useState(() =>
    Object.fromEntries(Object.keys(emptyProfile).map((key) => [key, initial?.[key] || ''])),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [linkDrawing, setLinkDrawing] = useState(() => Boolean(occurrence));
  const linkIssue = occurrence ? occurrenceLinkIssue(occurrence, draft.project) : '';
  const save = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      if (initial?.id) {
        const saved = await updateAsset(initial.id, { ...draft, version: initial.version });
        onSaved(saved, false);
      } else {
        const payload = assetCreatePayload(draft, occurrence, linkDrawing);
        const saved = await createAsset(payload);
        onSaved(saved, Boolean(payload.occurrence));
      }
    } catch (cause) {
      setError(cause.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <form className="asset-form" onSubmit={save}>
      <fieldset disabled={busy}>
        {fields.map(([key, label, maxLength, required]) => (
          <label key={key}>
            {label}
            <input
              value={draft[key]}
              required={required}
              maxLength={maxLength}
              onChange={(event) => setDraft({ ...draft, [key]: event.target.value })}
            />
          </label>
        ))}
        <label>
          Ghi chú
          <textarea
            rows={3}
            maxLength={10000}
            value={draft.notes}
            onChange={(event) => setDraft({ ...draft, notes: event.target.value })}
          />
        </label>
        <p className="asset-muted">
          Tag là duy nhất trong mỗi dự án và khu vực. Sửa hồ sơ không sửa nội dung tag trên bản vẽ.
        </p>
        {occurrence && !initial?.id && (
          <>
            <label className="asset-checkbox">
              <input
                type="checkbox"
                checked={linkDrawing}
                onChange={(event) => setLinkDrawing(event.target.checked)}
              />
              Liên kết với vị trí đang chọn
            </label>
            <p className={linkDrawing && linkIssue ? 'asset-stale' : 'asset-muted'}>
              {(linkDrawing && linkIssue) ||
                (linkDrawing
                  ? 'Lưu hồ sơ và liên kết với vị trí đang chọn. Tag và dự án trên bản vẽ được giữ nguyên.'
                  : 'Lưu hồ sơ độc lập. Có thể liên kết bản vẽ sau.')}
            </p>
          </>
        )}
        <div className="asset-actions">
          <button className="asset-primary">{busy ? 'Đang lưu…' : 'Lưu hồ sơ'}</button>
          {onCancel && (
            <button type="button" onClick={onCancel}>
              Hủy
            </button>
          )}
        </div>
      </fieldset>
      {error && (
        <p role="alert" className="asset-error">
          {error}
        </p>
      )}
    </form>
  );
}

function Attachments({ asset, onChanged }) {
  const [mode, setMode] = useState('upload');
  const [title, setTitle] = useState('');
  const [category, setCategory] = useState('datasheet');
  const [url, setUrl] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [deleteId, setDeleteId] = useState(null);
  const formRef = useRef(null);
  const save = async (event) => {
    event.preventDefault();
    setError('');
    const file = formRef.current.elements.file?.files?.[0];
    if (mode === 'upload' && (!file || file.size > 20 * 1024 * 1024)) {
      setError('Chọn tệp có dung lượng tối đa 20 MB.');
      return;
    }
    setBusy(true);
    try {
      if (mode === 'upload') await uploadAssetDocument(asset.id, file, { title, category });
      else await addDocumentLink(asset.id, { title, category, url });
      setTitle('');
      setUrl('');
      formRef.current.reset();
      onChanged('Đã thêm tài liệu.');
    } catch (cause) {
      setError(cause.message);
    } finally {
      setBusy(false);
    }
  };
  const remove = async (id) => {
    setBusy(true);
    setError('');
    try {
      await deleteAssetDocument(asset.id, id);
      setDeleteId(null);
      onChanged('Đã xóa tài liệu.');
    } catch (cause) {
      setError(cause.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="asset-section">
      <h3>
        <FolderOpen size={17} /> Tài liệu ({asset.documents.length})
      </h3>
      {!asset.documents.length && (
        <p className="asset-muted">Thêm datasheet, hướng dẫn hoặc ảnh hiện trường cho thiết bị.</p>
      )}
      <ul className="asset-document-list">
        {asset.documents.map((document) => (
          <li key={document.id}>
            <a
              href={document.url || assetDocumentUrl(asset.id, document.id)}
              target={document.url ? '_blank' : undefined}
              rel="noopener noreferrer"
            >
              <FileText size={16} />
              <span>
                <strong>{document.title}</strong>
                <small>
                  {categories[document.category]}
                  {document.filename &&
                    ` · ${document.filename} · ${(document.byte_size / 1024).toFixed(0)} KB`}
                </small>
              </span>
              {document.filename && <Download size={15} />}
            </a>
            {deleteId === document.id ? (
              <div className="asset-actions">
                <span>Xóa tài liệu này?</span>
                <button disabled={busy} onClick={() => remove(document.id)}>
                  Xóa
                </button>
                <button disabled={busy} onClick={() => setDeleteId(null)}>
                  Hủy
                </button>
              </div>
            ) : (
              <button
                className="asset-text-button"
                disabled={busy}
                onClick={() => setDeleteId(document.id)}
              >
                Xóa tài liệu
              </button>
            )}
          </li>
        ))}
      </ul>
      <details>
        <summary>+ Thêm tài liệu</summary>
        <form ref={formRef} className="asset-form" onSubmit={save}>
          <fieldset disabled={busy}>
            <label>
              Cách thêm
              <select value={mode} onChange={(event) => setMode(event.target.value)}>
                <option value="upload">Upload tệp</option>
                <option value="link">Gắn đường dẫn</option>
              </select>
            </label>
            <label>
              Tiêu đề{mode === 'upload' ? ' (có thể để trống)' : ''}
              <input
                value={title}
                required={mode === 'link'}
                maxLength={240}
                onChange={(event) => setTitle(event.target.value)}
              />
            </label>
            <label>
              Loại tài liệu
              <select value={category} onChange={(event) => setCategory(event.target.value)}>
                {Object.entries(categories).map(([key, label]) => (
                  <option key={key} value={key}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            {mode === 'upload' ? (
              <label>
                Tệp · tối đa 20 MB
                <input
                  name="file"
                  type="file"
                  required
                  accept=".pdf,.png,.jpg,.jpeg,.webp,.tif,.tiff,.doc,.docx,.xls,.xlsx,.csv,.txt"
                />
              </label>
            ) : (
              <label>
                Đường dẫn HTTP/HTTPS
                <input
                  type="url"
                  value={url}
                  required
                  maxLength={2048}
                  onChange={(event) => setUrl(event.target.value)}
                  placeholder="https://…"
                />
              </label>
            )}
            <button className="asset-primary">{busy ? 'Đang lưu…' : 'Thêm tài liệu'}</button>
          </fieldset>
        </form>
      </details>
      {error && (
        <p role="alert" className="asset-error">
          {error}
        </p>
      )}
    </section>
  );
}

function AssetDetails({ id, refresh, onChanged, onOpenOccurrence, onLinkDrawing, onLoaded }) {
  const [asset, setAsset] = useState(null);
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [removeId, setRemoveId] = useState(null);
  useEffect(() => {
    const controller = new AbortController();
    getAsset(id, controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return;
        setAsset(data);
        setError('');
        onLoaded(data);
      })
      .catch((cause) => {
        if (cause.name !== 'AbortError') setError(cause.message);
      });
    return () => controller.abort();
  }, [id, refresh, onLoaded]);
  const remove = async (linkId) => {
    setBusy(true);
    setError('');
    try {
      await unlinkOccurrence(id, linkId);
      setRemoveId(null);
      onChanged('Đã gỡ liên kết bản vẽ.');
    } catch (cause) {
      setError(cause.message);
    } finally {
      setBusy(false);
    }
  };
  const removeButton = (linkId) =>
    removeId === linkId ? (
      <div className="asset-actions">
        <span>Gỡ vị trí khỏi hồ sơ?</span>
        <button disabled={busy} onClick={() => remove(linkId)}>
          Gỡ
        </button>
        <button disabled={busy} onClick={() => setRemoveId(null)}>
          Hủy
        </button>
      </div>
    ) : (
      <button className="asset-text-button" disabled={busy} onClick={() => setRemoveId(linkId)}>
        <Unlink size={12} /> Gỡ liên kết
      </button>
    );
  if (!asset) return <p role={error ? 'alert' : 'status'}>{error || 'Đang tải hồ sơ…'}</p>;
  return (
    <>
      <div className="asset-profile-heading">
        <div>
          <small>HỒ SƠ THIẾT BỊ</small>
          <h2>{asset.tag}</h2>
        </div>
        <button onClick={() => setEditing(!editing)}>
          {editing ? 'Đóng chỉnh sửa' : 'Chỉnh sửa'}
        </button>
      </div>
      {error && (
        <p role="alert" className="asset-error">
          {error}
        </p>
      )}
      {editing ? (
        <AssetForm
          key={asset.version}
          initial={asset}
          onSaved={() => {
            setEditing(false);
            onChanged('Đã lưu hồ sơ.');
          }}
          onCancel={() => setEditing(false)}
        />
      ) : (
        <>
          <h3>{asset.name || 'Chưa đặt tên thiết bị'}</h3>
          <dl className="asset-properties">
            <dt>Dự án</dt>
            <dd>{asset.project}</dd>
            <dt>Khu vực</dt>
            <dd>{asset.area || '—'}</dd>
            <dt>Loại</dt>
            <dd>{asset.equipment_type || '—'}</dd>
            <dt>Cập nhật</dt>
            <dd>{new Date(asset.updated_at).toLocaleString('vi-VN')}</dd>
          </dl>
          {asset.notes && <p className="asset-notes">{asset.notes}</p>}
        </>
      )}
      <section className="asset-section">
        <h3>Vị trí trên P&amp;ID ({asset.occurrences.length})</h3>
        {!asset.occurrences.length && (
          <p className="asset-muted">
            Hồ sơ chưa có vị trí bản vẽ. Chọn “Liên kết bản vẽ” để tìm và gắn symbol vào hồ sơ.
          </p>
        )}
        <button className="asset-primary" onClick={() => onLinkDrawing(asset)}>
          <Plus size={14} /> Liên kết bản vẽ
        </button>
        {asset.occurrences.map((item) => (
          <div className="asset-location" key={item.link_id}>
            <button className="asset-location-open" onClick={() => onOpenOccurrence(item)}>
              {locationLabel(item)}
              <small>
                {item.tag || item.symbol_code} ·{' '}
                {item.source === 'review' ? 'Review' : 'Nhãn đã lưu'} ·{' '}
                {item.lifecycle === 'superseded' ? 'Đã thay thế' : 'Đang sử dụng'}
              </small>
            </button>
            {removeButton(item.link_id)}
          </div>
        ))}
        {asset.stale_links.length > 0 && (
          <div className="asset-stale">
            <strong>{asset.stale_links.length} liên kết cần kiểm tra lại</strong>
            <p>Tag, dự án hoặc kết quả nguồn đã thay đổi. Tìm lại vị trí trước khi liên kết.</p>
            {asset.stale_links.map((item) => (
              <div key={item.id}>
                Trang {item.page_number} · {item.drawing_id.slice(0, 8)}
                {removeButton(item.id)}
              </div>
            ))}
          </div>
        )}
      </section>
      <Attachments asset={asset} onChanged={onChanged} />
    </>
  );
}

function AssetOccurrenceLinker({ asset, occurrence, onLinked, onCancel }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const issue = occurrenceLinkIssue(occurrence, asset.project);
  const linkedElsewhere = occurrence?.asset_id && occurrence.asset_id !== asset.id;
  const alreadyLinked = occurrence?.asset_id === asset.id;
  const attach = async () => {
    setBusy(true);
    setError('');
    try {
      await linkOccurrence(asset.id, occurrence);
      onLinked();
    } catch (cause) {
      setError(cause.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <h2>Liên kết bản vẽ cho {asset.tag}</h2>
      <p className="asset-muted">Dự án: {asset.project}</p>
      <p>Tìm tag hoặc mã symbol ở bên trái, chọn đúng vị trí rồi bấm “Xác nhận liên kết”.</p>
      {occurrence && (
        <section className="asset-section">
          <strong>{occurrence.tag || occurrence.symbol_code}</strong>
          <p>{locationLabel(occurrence)}</p>
          <p className="asset-muted">
            Có thể liên kết thủ công khi symbol chưa có tag hoặc bản vẽ chưa có dự án. Liên kết
            không thay đổi nhãn hay dự án trên bản vẽ.
          </p>
        </section>
      )}
      <p className="asset-muted" role="status">
        {linkedElsewhere
          ? 'Vị trí này đã thuộc hồ sơ khác. Gỡ liên kết cũ trước khi chuyển hồ sơ.'
          : alreadyLinked
            ? 'Vị trí này đã được liên kết với hồ sơ.'
            : issue}
      </p>
      <div className="asset-actions">
        <button
          className="asset-primary"
          disabled={busy || Boolean(issue) || Boolean(linkedElsewhere) || alreadyLinked}
          onClick={attach}
        >
          {busy ? 'Đang liên kết…' : 'Xác nhận liên kết'}
        </button>
        <button disabled={busy} onClick={onCancel}>
          Hủy liên kết
        </button>
      </div>
      {error && (
        <p className="asset-error" role="alert">
          {error}
        </p>
      )}
    </>
  );
}

function LinkOrCreate({ occurrence, project, onSaved }) {
  const [query, setQuery] = useState(occurrence?.tag || '');
  const [candidates, setCandidates] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const canLink = Boolean(occurrence);
  useEffect(() => {
    if (!canLink) return undefined;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      listAssets({ q: query, project: occurrence.project }, controller.signal)
        .then((result) => setCandidates(result.items))
        .catch((cause) => {
          if (cause.name !== 'AbortError') setError(cause.message);
        });
    }, 250);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [occurrence, query, canLink]);
  const attach = async (id) => {
    setBusy(true);
    setError('');
    try {
      await linkOccurrence(id, occurrence);
      onSaved({ id }, true);
    } catch (cause) {
      setError(cause.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <h2>
        {occurrence
          ? `Hồ sơ cho ${occurrence.tag || occurrence.symbol_code}`
          : 'Tạo hồ sơ thiết bị'}
      </h2>
      {canLink && (
        <section className="asset-section">
          <h3>Gắn vào hồ sơ hiện có</h3>
          <label>
            Tìm hồ sơ
            <input
              value={query}
              maxLength={120}
              onChange={(event) => setQuery(event.target.value)}
            />
          </label>
          {candidates.map((item) => (
            <button
              className="asset-link-candidate"
              key={item.id}
              disabled={busy || Boolean(occurrenceLinkIssue(occurrence, item.project))}
              onClick={() => attach(item.id)}
            >
              <strong>{item.tag}</strong> · {item.area || 'Chưa có khu vực'}
              <small>{item.name || item.equipment_type}</small>
            </button>
          ))}
          {!candidates.length && <p className="asset-muted">Chưa tìm thấy hồ sơ phù hợp.</p>}
          {error && (
            <p className="asset-error" role="alert">
              {error}
            </p>
          )}
        </section>
      )}
      <h3>{canLink ? 'Hoặc tạo hồ sơ mới' : 'Thông tin thiết bị'}</h3>
      <AssetForm
        initial={{
          ...emptyProfile,
          project: occurrence?.project || project,
          tag: occurrence?.tag || '',
          equipment_type: occurrence?.equipment_type || '',
        }}
        occurrence={occurrence}
        onSaved={onSaved}
      />
    </>
  );
}

export default function AssetWorkspace({ hidden }) {
  const [query, setQuery] = useState('');
  const [project, setProject] = useState('');
  const [projects, setProjects] = useState([]);
  const [mode, setMode] = useState('tags');
  const [includeOld, setIncludeOld] = useState(false);
  const [offset, setOffset] = useState(0);
  const [result, setResult] = useState({ items: [], total: 0, queryKey: '' });
  const [error, setError] = useState('');
  const [refresh, setRefresh] = useState(0);
  const [occurrence, setOccurrence] = useState(null);
  const [assetId, setAssetId] = useState(null);
  const [linkTarget, setLinkTarget] = useState(null);
  const [assetSelection, setAssetSelection] = useState(0);
  const [creating, setCreating] = useState(false);
  const [drawingResult, setDrawingResult] = useState({ key: '', data: null, error: '' });
  const [notice, setNotice] = useState('');
  const canvas = useRef(null);
  const queryKey = JSON.stringify([query, project, mode, includeOld, offset, refresh]);
  const loading = result.queryKey !== queryKey;
  const drawingId = occurrence?.drawing_id;
  const pageNumber = occurrence?.page_number;
  const drawingKey = drawingId ? `${drawingId}-${pageNumber}-${refresh}` : '';
  const drawing = drawingResult.key === drawingKey ? drawingResult.data : null;
  const viewerError = drawingResult.key === drawingKey ? drawingResult.error : '';
  const assetLoaded = useCallback((asset) => {
    setOccurrence((current) => {
      const saved = asset.occurrences.find((item) => sourceKey(item) === sourceKey(current));
      if (saved) return saved;
      if (current?.asset_id === asset.id) return asset.occurrences[0] || null;
      return current || asset.occurrences[0] || null;
    });
  }, []);
  useEffect(() => {
    if (hidden) return undefined;
    let cancelled = false;
    getDocuments()
      .then((items) => {
        if (!cancelled)
          setProjects([...new Set(items.map((item) => item.project).filter(Boolean))].sort());
      })
      .catch((cause) => {
        if (!cancelled) setError(cause.message);
      });
    return () => {
      cancelled = true;
    };
  }, [hidden, refresh]);
  useEffect(() => {
    if (hidden) return undefined;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setError('');
      const operation = mode === 'tags' ? searchTags : listAssets;
      operation(
        {
          q: query,
          project,
          offset,
          limit: 50,
          ...(mode === 'tags' ? { include_superseded: includeOld } : {}),
        },
        controller.signal,
      )
        .then((data) => {
          if (controller.signal.aborted) return;
          setResult({ ...data, queryKey });
        })
        .catch((cause) => {
          if (cause.name !== 'AbortError') {
            setError(cause.message);
            setResult({ items: [], total: 0, queryKey });
          }
        });
    }, 250);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [query, project, mode, includeOld, offset, refresh, hidden, queryKey]);
  useEffect(() => {
    if (hidden || !drawingId) return undefined;
    let cancelled = false;
    getDocumentPage(drawingId, pageNumber)
      .then((data) => {
        if (!cancelled) setDrawingResult({ key: drawingKey, data, error: '' });
      })
      .catch((cause) => {
        if (!cancelled) setDrawingResult({ key: drawingKey, data: null, error: cause.message });
      });
    return () => {
      cancelled = true;
    };
  }, [drawingId, pageNumber, drawingKey, hidden]);
  useEffect(() => {
    if (!notice) return undefined;
    const timer = window.setTimeout(() => setNotice(''), 4500);
    return () => window.clearTimeout(timer);
  }, [notice]);
  const changed = (message) => {
    setNotice(message);
    setRefresh((value) => value + 1);
  };
  const chooseOccurrence = (item) => {
    setOccurrence(item);
    if (linkTarget) return;
    setAssetId(item.asset_id || null);
    setCreating(!item.asset_id);
  };
  const chooseAsset = (item) => {
    setLinkTarget(null);
    setAssetSelection((value) => value + 1);
    setAssetId(item.id);
    setCreating(false);
    setOccurrence(null);
  };
  const saved = (asset, linked = false) => {
    setLinkTarget(null);
    setAssetId(asset.id);
    setCreating(false);
    changed(linked ? 'Đã lưu hồ sơ và liên kết.' : 'Đã lưu hồ sơ độc lập.');
  };
  const changeFilter = (setter, value) => {
    setter(value);
    setOffset(0);
  };
  const changeMode = (value) => {
    setMode(value);
    setQuery('');
    setOffset(0);
    if (value === 'profiles') setLinkTarget(null);
  };
  const startLinking = (asset) => {
    setLinkTarget(asset);
    setAssetId(asset.id);
    setCreating(false);
    setOccurrence(null);
    setMode('tags');
    setQuery('');
    setProject('');
    setOffset(0);
  };
  if (hidden) return null;
  return (
    <main className="asset-workspace">
      <header className="asset-workspace-heading">
        <div>
          <h1>Thiết bị &amp; hồ sơ</h1>
          <p>Tra cứu tag trên P&amp;ID và mở tài liệu của thiết bị.</p>
        </div>
        <div className="asset-actions">
          <button onClick={() => changed('Đã làm mới dữ liệu.')}>
            <RefreshCw size={15} /> Làm mới
          </button>
          <button
            className="asset-primary"
            onClick={() => {
              setAssetId(null);
              setLinkTarget(null);
              setOccurrence(null);
              setCreating(true);
            }}
          >
            <Plus size={16} /> Tạo hồ sơ
          </button>
        </div>
      </header>
      {notice && (
        <p className="asset-notice" role="status">
          {notice}
        </p>
      )}
      <div className="asset-layout">
        <aside className="asset-search-panel">
          <div className="asset-mode-tabs" role="group" aria-label="Loại tìm kiếm">
            <button aria-pressed={mode === 'tags'} onClick={() => changeMode('tags')}>
              Tag / mã symbol
            </button>
            <button aria-pressed={mode === 'profiles'} onClick={() => changeMode('profiles')}>
              Hồ sơ thiết bị
            </button>
          </div>
          <label className="asset-search-input">
            <Search size={16} />
            <input
              aria-label="Tìm tag, mã symbol hoặc hồ sơ"
              value={query}
              maxLength={120}
              placeholder={
                mode === 'tags'
                  ? 'Tag hoặc mã symbol, VD: VALVES-019'
                  : 'Tag, tên, loại hoặc khu vực…'
              }
              onChange={(event) => changeFilter(setQuery, event.target.value)}
            />
          </label>
          <label>
            Dự án
            <select
              value={project}
              onChange={(event) => changeFilter(setProject, event.target.value)}
            >
              <option value="">Tất cả dự án</option>
              {projects.map((name) => (
                <option key={name}>{name}</option>
              ))}
            </select>
          </label>
          {mode === 'tags' && (
            <label className="asset-checkbox">
              <input
                type="checkbox"
                checked={includeOld}
                onChange={(event) => changeFilter(setIncludeOld, event.target.checked)}
              />{' '}
              Bao gồm bản đã thay thế
            </label>
          )}
          <p className="asset-muted" role="status">
            {loading ? 'Đang tìm…' : `${result.total} kết quả`}
          </p>
          {error && (
            <p role="alert" className="asset-error">
              {error}
            </p>
          )}
          <div className="asset-results" aria-busy={loading}>
            {!loading && !error && !result.items.length && (
              <p className="asset-empty">
                {mode === 'tags'
                  ? 'Chưa tìm thấy tag hoặc mã symbol trong nhãn và review đã lưu. Kiểm tra bộ lọc hoặc lưu nhãn rồi tìm lại.'
                  : 'Chưa có hồ sơ phù hợp. Chọn “Tạo hồ sơ” để thêm thiết bị.'}
              </p>
            )}
            {!loading &&
              !error &&
              result.items.map((item) => (
                <button
                  key={mode === 'tags' ? sourceKey(item) : item.id}
                  className={`asset-result ${mode === 'tags' ? (sourceKey(occurrence) === sourceKey(item) ? 'is-active' : '') : assetId === item.id ? 'is-active' : ''}`}
                  onClick={() => (mode === 'tags' ? chooseOccurrence(item) : chooseAsset(item))}
                >
                  <strong>{item.tag || item.asset_tag || item.symbol_code}</strong>
                  <span>
                    {item.name ||
                      item.equipment_type ||
                      (item.kind === 'text' ? 'OCR chưa gắn symbol' : 'Thiết bị')}
                  </span>
                  <small>
                    {item.project || item.asset_project || 'Chưa có dự án'}
                    {item.area && ` / ${item.area}`}
                  </small>
                  {mode === 'tags' && (
                    <>
                      <small>{locationLabel(item)}</small>
                      {item.symbol_code && <small>Mã symbol: {item.symbol_code}</small>}
                      <div className="asset-result-badges">
                        <span>{statuses[item.review_status] || item.review_status}</span>
                        <span>
                          {item.asset_id
                            ? 'Có hồ sơ'
                            : !item.tag
                              ? 'Chưa có tag thiết bị'
                              : 'Chưa liên kết'}
                        </span>
                        {item.lifecycle === 'superseded' && (
                          <span className="asset-old">Đã thay thế</span>
                        )}
                      </div>
                    </>
                  )}
                </button>
              ))}
          </div>
          <div className="asset-pagination">
            <button
              disabled={loading || offset === 0}
              onClick={() => setOffset(Math.max(0, offset - 50))}
            >
              Trước
            </button>
            <span>
              {result.total ? `${offset + 1}–${Math.min(offset + 50, result.total)}` : '0'} /{' '}
              {result.total}
            </span>
            <button
              disabled={loading || offset + 50 >= result.total}
              onClick={() => setOffset(offset + 50)}
            >
              Sau
            </button>
          </div>
        </aside>
        <section className="asset-viewer-panel">
          <div className="asset-viewer-toolbar">
            <span>{occurrence ? locationLabel(occurrence) : 'Vị trí trên P&ID'}</span>
            <div className="asset-actions">
              <button title="Thu nhỏ" onClick={() => canvas.current?.zoomOut()} disabled={!drawing}>
                <ZoomOut size={15} />
              </button>
              <button title="Phóng to" onClick={() => canvas.current?.zoomIn()} disabled={!drawing}>
                <ZoomIn size={15} />
              </button>
              <button onClick={() => canvas.current?.fit()} disabled={!drawing}>
                Vừa trang
              </button>
            </div>
          </div>
          {drawing && occurrence ? (
            <TiledDrawingCanvas
              key={`${drawing.id}-${drawing.page_number}`}
              ref={canvas}
              drawing={drawing}
              focusBox={occurrence.box}
              panOnly
              centerOnResize
              viewerHint="Kéo để di chuyển · Lăn chuột để zoom · Khung vàng là vị trí tag"
            />
          ) : (
            <div className="asset-viewer-empty">
              <Search size={32} />
              <p>
                {viewerError ||
                  (occurrence
                    ? 'Đang mở bản vẽ…'
                    : linkTarget
                      ? 'Chọn một symbol bên trái để xem và liên kết với hồ sơ.'
                      : assetId
                        ? 'Hồ sơ chưa có vị trí bản vẽ. Bấm “Liên kết bản vẽ” trong hồ sơ để chọn vị trí.'
                        : 'Chọn một kết quả tag hoặc vị trí trong hồ sơ để xem bản vẽ.')}
              </p>
            </div>
          )}
          {occurrence && (
            <div className="asset-source-note">
              {occurrence.lifecycle === 'superseded' && <strong>Bản vẽ đã được thay thế. </strong>}
              Nguồn:{' '}
              {occurrence.source === 'review'
                ? 'kết quả đã lưu review'
                : 'nhãn OCR/symbol đã lưu'}{' '}
              · {statuses[occurrence.review_status] || occurrence.review_status}
              {occurrence.kind === 'text' && ' · OCR chưa được gắn với symbol.'}
              {!occurrence.tag && ' · Symbol chưa có tag thiết bị.'}
            </div>
          )}
        </section>
        <aside className="asset-detail-panel">
          {linkTarget ? (
            <AssetOccurrenceLinker
              key={`${linkTarget.id}-${sourceKey(occurrence)}`}
              asset={linkTarget}
              occurrence={occurrence}
              onLinked={() => {
                setOccurrence({ ...occurrence, asset_id: linkTarget.id });
                setLinkTarget(null);
                changed('Đã liên kết vị trí bản vẽ với hồ sơ.');
              }}
              onCancel={() => {
                setLinkTarget(null);
                setOccurrence(null);
              }}
            />
          ) : assetId ? (
            <AssetDetails
              key={`${assetId}-${assetSelection}`}
              id={assetId}
              refresh={refresh}
              onChanged={changed}
              onOpenOccurrence={(item) => setOccurrence(item)}
              onLinkDrawing={startLinking}
              onLoaded={assetLoaded}
            />
          ) : creating ? (
            <LinkOrCreate
              key={sourceKey(occurrence) || `new-${project}`}
              occurrence={occurrence}
              project={project}
              onSaved={saved}
            />
          ) : (
            <div className="asset-empty">
              <FolderOpen size={28} />
              <h2>Hồ sơ thiết bị</h2>
              <p>
                Chọn tag để xem hoặc tạo hồ sơ, sau đó gắn tài liệu và các vị trí trên P&amp;ID.
              </p>
            </div>
          )}
        </aside>
      </div>
    </main>
  );
}
