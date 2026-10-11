import { useEffect, useRef, useState } from 'react';
import { Download, X } from 'lucide-react';
import SymbolPreview from './SymbolPreview';

function formatDate(value) {
  const date = new Date(value);
  if (!value || Number.isNaN(date.getTime())) return '—';
  return new Intl.DateTimeFormat('vi-VN', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'Asia/Ho_Chi_Minh',
  }).format(date);
}

export default function SymbolDetailsDialog({ symbol, onClose }) {
  const dialogRef = useRef(null);
  const [imageFailed, setImageFailed] = useState(false);

  useEffect(() => {
    const dialog = dialogRef.current;
    const previousFocus = document.activeElement;
    dialog.showModal();
    return () => {
      dialog.close();
      if (previousFocus instanceof HTMLElement && previousFocus.isConnected) previousFocus.focus();
    };
  }, []);

  return (
    <dialog
      ref={dialogRef}
      className="symbol-details-dialog"
      aria-labelledby="symbol-details-title"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onKeyDown={(event) => {
        if (event.key !== 'Tab') return;
        const controls = event.currentTarget.querySelectorAll('button:not(:disabled), a[href]');
        const first = controls[0];
        const last = controls[controls.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }}
      onClick={(event) => {
        if (event.target !== event.currentTarget) return;
        const bounds = event.currentTarget.getBoundingClientRect();
        if (
          event.clientX < bounds.left ||
          event.clientX > bounds.right ||
          event.clientY < bounds.top ||
          event.clientY > bounds.bottom
        )
          onClose();
      }}
    >
      <header className="symbol-details-header">
        <div>
          <small>THƯ VIỆN SYMBOL</small>
          <h2 id="symbol-details-title">Chi tiết symbol</h2>
        </div>
        <button
          type="button"
          className="symbol-details-close"
          onClick={onClose}
          aria-label="Đóng chi tiết symbol"
        >
          <X size={20} />
        </button>
      </header>
      <div className="symbol-details-body">
        <section className="symbol-details-visual" aria-label="Hình ảnh symbol">
          <h3>Ảnh xem trước</h3>
          <div className="symbol-details-image" role="img" aria-label={`Ảnh symbol ${symbol.name}`}>
            {imageFailed || !symbol.preview ? (
              <p>Không tải được ảnh symbol.</p>
            ) : (
              <SymbolPreview symbol={symbol} expanded onError={() => setImageFailed(true)} />
            )}
          </div>
        </section>
        <dl className="symbol-details-info">
          <div>
            <dt>Mã symbol</dt>
            <dd>
              <code>{symbol.code}</code>
            </dd>
          </div>
          <div>
            <dt>Tên symbol</dt>
            <dd>{symbol.name}</dd>
          </div>
          <div>
            <dt>Nhóm</dt>
            <dd>{symbol.category}</dd>
          </div>
          <div>
            <dt>Trạng thái</dt>
            <dd>
              <span className={`symbol-details-status ${symbol.enabled ? 'is-on' : ''}`}>
                {symbol.enabled ? 'Đang bật' : 'Đang tắt'}
              </span>
            </dd>
          </div>
          <div>
            <dt>Nguồn</dt>
            <dd>{symbol.origin === 'web-import' ? 'Nhập từ ứng dụng' : symbol.origin || '—'}</dd>
          </div>
          <div>
            <dt>Ngày tạo</dt>
            <dd>{formatDate(symbol.created_at)}</dd>
          </div>
          <div>
            <dt>Cập nhật lần cuối</dt>
            <dd>{formatDate(symbol.updated_at)}</dd>
          </div>
        </dl>
      </div>
      <footer className="symbol-details-footer">
        <a href={symbol.source_url}>
          <Download size={15} /> Tải file gốc
        </a>
        <button type="button" onClick={onClose}>
          Đóng
        </button>
      </footer>
    </dialog>
  );
}
