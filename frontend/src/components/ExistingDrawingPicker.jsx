import { useEffect, useRef, useState } from 'react';
import { FileText, RefreshCw, Search, X } from 'lucide-react';
import { getDocuments } from '../services/annotations';

export default function ExistingDrawingPicker({ drawing, onChoose, onClose }) {
  const dialog = useRef(null);
  const [documents, setDocuments] = useState([]);
  const [selectedId, setSelectedId] = useState(drawing?.id || '');
  const [page, setPage] = useState(drawing?.page_number || 1);
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('all');
  const [loading, setLoading] = useState(true);
  const [opening, setOpening] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [error, setError] = useState('');

  useEffect(() => {
    const element = dialog.current;
    const previousFocus = document.activeElement;
    element.showModal();
    return () => {
      element.close();
      if (previousFocus instanceof HTMLElement && previousFocus.isConnected) previousFocus.focus();
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    getDocuments()
      .then((items) => {
        if (!cancelled) {
          setDocuments(items);
          setError('');
        }
      })
      .catch((cause) => {
        if (!cancelled) setError(cause.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [refresh]);

  const visible = documents.filter(
    (item) =>
      item.name.toLowerCase().includes(query.trim().toLowerCase()) &&
      (filter === 'all' || (filter === 'labeled' ? item.is_labeled : !item.is_labeled)),
  );
  const selected = visible.find((item) => item.id === selectedId);
  const selectedPage = selected && page <= selected.page_count ? page : 1;
  const open = async () => {
    if (!selected || opening) return;
    setOpening(true);
    setError('');
    const opened = await onChoose(selected.id, selectedPage);
    if (opened) onClose();
    else {
      setOpening(false);
      setError('Không thể mở bản vẽ. Vui lòng thử lại hoặc làm mới danh sách.');
    }
  };

  return (
    <dialog
      ref={dialog}
      className="annotation-drawing-dialog"
      aria-labelledby="existing-drawing-title"
      onCancel={(event) => {
        event.preventDefault();
        if (!opening) onClose();
      }}
    >
      <header>
        <div>
          <h2 id="existing-drawing-title">Chọn bản vẽ từ Data</h2>
          <p>Mở bản vẽ có sẵn để chỉnh sửa hoặc tiếp tục gán nhãn.</p>
        </div>
        <button aria-label="Đóng chọn bản vẽ" disabled={opening} onClick={onClose}>
          <X size={18} />
        </button>
      </header>
      <div className="annotation-drawing-filters">
        <label className="annotation-search">
          <Search size={16} />
          <input
            autoFocus
            aria-label="Tìm bản vẽ trong Data"
            placeholder="Tìm theo tên bản vẽ…"
            value={query}
            disabled={opening}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <select
          aria-label="Lọc trạng thái gán nhãn"
          value={filter}
          disabled={opening}
          onChange={(event) => setFilter(event.target.value)}
        >
          <option value="all">Tất cả bản vẽ</option>
          <option value="labeled">Đã gán nhãn</option>
          <option value="unlabeled">Chưa gán nhãn</option>
        </select>
        <button
          aria-label="Làm mới bản vẽ từ Data"
          disabled={loading || opening}
          onClick={() => {
            setLoading(true);
            setRefresh((value) => value + 1);
          }}
        >
          <RefreshCw size={16} />
        </button>
      </div>
      {error && (
        <p role="alert" className="annotation-notice is-error">
          {error}
        </p>
      )}
      <div className="annotation-drawing-options" aria-busy={loading}>
        {loading ? (
          <p>Đang tải danh sách bản vẽ…</p>
        ) : visible.length ? (
          visible.map((item) => (
            <label key={item.id} className={selectedId === item.id ? 'is-selected' : ''}>
              <input
                type="radio"
                name="existing-drawing"
                value={item.id}
                checked={selectedId === item.id}
                disabled={opening}
                onChange={() => {
                  setSelectedId(item.id);
                  setPage(1);
                }}
              />
              <FileText size={22} />
              <span>
                <strong>{item.name}</strong>
                <small>
                  {item.page_count} trang · {item.is_labeled ? 'Đã gán nhãn' : 'Chưa gán nhãn'}
                  {item.annotation_count > 0 && ` · ${item.annotation_count} nhãn`}
                </small>
              </span>
            </label>
          ))
        ) : (
          <p>
            {documents.length
              ? 'Không có bản vẽ phù hợp với tìm kiếm hoặc bộ lọc.'
              : 'Chưa có bản vẽ trong Data. Tải bản vẽ ở tab Data hoặc dùng Tải ảnh / PDF.'}
          </p>
        )}
      </div>
      <footer>
        {selected && (
          <label className="annotation-field">
            <span>Trang cần chỉnh sửa</span>
            <select
              aria-label="Trang cần chỉnh sửa"
              value={selectedPage}
              disabled={opening}
              onChange={(event) => setPage(Number(event.target.value))}
            >
              {Array.from({ length: selected.page_count }, (_, index) => (
                <option key={index + 1} value={index + 1}>
                  Trang {index + 1}
                </option>
              ))}
            </select>
          </label>
        )}
        <button
          className="annotation-open-drawing"
          disabled={!selected || loading || opening}
          onClick={open}
        >
          {opening ? 'Đang mở bản vẽ…' : 'Mở để chỉnh sửa'}
        </button>
      </footer>
    </dialog>
  );
}
