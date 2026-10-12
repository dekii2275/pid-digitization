import { useEffect, useRef, useState } from 'react';
import { Upload } from 'lucide-react';
import { uploadDrawingDocument } from '../services/documents';

const MAX_BYTES = 100 * 1024 * 1024;
const validate = (file) => {
  if (!/\.(pdf|png|jpe?g)$/i.test(file.name)) return 'Chỉ hỗ trợ PDF, PNG, JPG hoặc JPEG.';
  if (!file.size) return 'File trống.';
  if (file.size > MAX_BYTES) return 'File vượt giới hạn 100 MB.';
  return '';
};

export default function DrawingUploadPanel({ onUploaded, disabled }) {
  const [queue, setQueue] = useState([]);
  const [dragging, setDragging] = useState(false);
  const running = useRef(false);
  const callback = useRef(onUploaded);
  useEffect(() => {
    callback.current = onUploaded;
  }, [onUploaded]);

  useEffect(() => {
    const next = queue.find((item) => item.status === 'queued');
    if (!next || running.current || disabled) return;
    running.current = true;
    const change = (patch) =>
      setQueue((items) =>
        items.map((item) => (item.id === next.id ? { ...item, ...patch } : item)),
      );
    change({ status: 'uploading', progress: 0 });
    uploadDrawingDocument(next.file, {
      onProgress: (progress) => change({ progress }),
    })
      .then((document) => {
        change({ status: 'done', progress: 100, file: null });
        callback.current(document);
      })
      .catch((error) => change({ status: 'error', error: error.message }))
      .finally(() => {
        running.current = false;
        setQueue((items) => [...items]);
      });
  }, [queue, disabled]);

  const addFiles = (files) => {
    if (disabled) return;
    setQueue((items) => [
      ...items,
      ...Array.from(files).map((file) => {
        const error = validate(file);
        return {
          id: crypto.randomUUID(),
          file,
          name: file.name,
          status: error ? 'error' : 'queued',
          progress: 0,
          error,
          invalid: Boolean(error),
        };
      }),
    ]);
  };
  const retry = (id) =>
    setQueue((items) =>
      items.map((item) =>
        (id ? item.id === id : item.status === 'error') && !item.invalid
          ? { ...item, status: 'queued', progress: 0, error: '' }
          : item,
      ),
    );
  const active = queue.some((item) => ['queued', 'uploading'].includes(item.status));
  const failed = queue.filter((item) => item.status === 'error');

  return (
    <section className="drawing-upload-panel" aria-label="Upload nhiều bản vẽ">
      <label
        className={`drawing-dropzone ${dragging ? 'is-dragging' : ''} ${disabled ? 'is-disabled' : ''}`}
        onDragOver={(event) => {
          event.preventDefault();
          if (!disabled) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          addFiles(event.dataTransfer.files);
        }}
      >
        <Upload size={20} />
        <span>
          <strong>Kéo thả bản vẽ vào đây hoặc chọn nhiều file</strong>
          <small>PDF, PNG, JPG · Tối đa 100 MB/file</small>
        </span>
        <input
          type="file"
          multiple
          accept=".pdf,.png,.jpg,.jpeg"
          aria-label="Chọn nhiều bản vẽ"
          disabled={disabled}
          onChange={(event) => {
            addFiles(event.target.files);
            event.target.value = '';
          }}
        />
      </label>
      {queue.length > 0 && (
        <details className="drawing-upload-queue" open={active || failed.length > 0}>
          <summary aria-live="polite">
            Đã tải {queue.filter((item) => item.status === 'done').length}/{queue.length} file
            {failed.length > 0 && ` · ${failed.length} lỗi`}
          </summary>
          <div className="drawing-upload-actions">
            {failed.some((item) => !item.invalid) && (
              <button disabled={disabled} onClick={() => retry()}>
                Thử lại các file lỗi
              </button>
            )}
            {!active && <button onClick={() => setQueue([])}>Dọn danh sách upload</button>}
          </div>
          <ul>
            {queue.map((item) => (
              <li key={item.id}>
                <strong title={item.name}>{item.name}</strong>
                {item.status === 'uploading' && (
                  <progress max="100" value={item.progress} aria-label={`Tiến độ ${item.name}`} />
                )}
                <span role={item.status === 'error' ? 'alert' : undefined}>
                  {item.status === 'queued'
                    ? 'Đang chờ'
                    : item.status === 'done'
                      ? 'Đã tải'
                      : item.status === 'error'
                        ? item.error
                        : item.progress === 100
                          ? 'Đang xử lý bản vẽ…'
                          : `${item.progress}%`}
                </span>
                {item.status === 'error' && !item.invalid && (
                  <button disabled={disabled} onClick={() => retry(item.id)}>
                    Thử lại
                  </button>
                )}
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
