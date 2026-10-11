# Data: drawing management

The **Data** tab combines the former Data/View sections. Upload a PDF, search the
drawing list, filter **Đã gán nhãn**, and select a drawing to view its pages.
Saved symbol/OCR boxes and relations appear in the preview. **Gán nhãn** opens the
existing Generate data workspace; only saved annotations affect the Data filter.
An empty saved page remains an unlabeled negative training example.

Original PDF/image bytes live in the private MinIO bucket (`MINIO_BUCKET`, default
`pid-drawings`). PostgreSQL stores the bucket, object key, size, SHA-256, timestamps,
render settings, manual annotations and stable YOLO class mapping. File links are
served through the backend. The browser never receives MinIO credentials.
Local uploads, previews and tiles are caches; the backend restores originals from
MinIO when needed. PDF rendering retains each document's stored DPI and pixel
limit so existing annotations keep their coordinates. New PDFs render at 144 DPI,
capped at 16 million pixels per page. The viewer selects tiles for the current
zoom without requesting an extra sharper level.

Docker Compose starts MinIO with persistent `minio_data` storage. Its image is
built from pinned [official MinIO source](https://github.com/minio/minio/tree/RELEASE.2025-09-07T16-13-09Z).
Set `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`, and `MINIO_BUCKET` in `.env`.
MinIO's API and console are bound to localhost ports 18735 and 18736 by default.
For a backend outside Compose, set `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`,
`MINIO_SECRET_KEY`, and `MINIO_SECURE` alongside the existing `POSTGRES_*` settings.
Install `src/requirements.storage.txt` with the web and symbol database requirements.

On the first startup, a transaction imports legacy local drawing metadata,
sources and saved annotations. Source files are retained as backups. A database
migration marker prevents deleted legacy drawings from returning on restart.
Back up both PostgreSQL and the MinIO volume.

API endpoints:

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/documents/upload` | Upload PDF/image, maximum 100 MB |
| GET | `/api/v1/documents?labeled=true` | List drawings with saved symbol/OCR annotations |
| GET | `/api/v1/documents?labeled=false` | List drawings without saved symbol/OCR annotations |
| GET | `/api/v1/documents/{id}` | Drawing metadata and annotation summary |
| GET | `/api/v1/documents/{id}/original` | Download original bytes from MinIO |
| GET | `/api/v1/documents/{id}/pages/{page}` | Page dimensions and preview/tile links |
| DELETE | `/api/v1/documents/{id}` | Delete original, metadata, annotations and cached artifacts |

Deletion is blocked while a pipeline job is queued/running. Storage failures
return HTTP 503; an unsuccessful MinIO deletion retains the catalog entry so the
user can retry. Uploads clean up the object if the database insert fails.

Verify a running stack with `python scripts/smoke_data.py`. The script uploads its
own two-page PDF, saves OCR labels, checks filtering/download/export, then deletes
its test drawing.
