# Data: drawing management

The **Data** tab combines the former Data/View sections. Upload a PDF, search the
drawing list, filter **Đã gán nhãn**, and select a drawing to view its pages.
Saved symbol/OCR boxes and relations appear in the preview. **Gán nhãn** opens the
existing Generate data workspace; only saved annotations affect the Data filter.
An empty saved page remains an unlabeled negative training example.

## Bố cục Data

Data có ba tab riêng:

- **Bản vẽ**: vùng xem chiếm toàn bộ chiều ngang, bản vẽ căn giữa; các nút
  chuyển trang, gán nhãn, zoom và tải file gốc nằm trên thanh công cụ gọn.
  Bấm **Danh sách bản vẽ** để mở thư viện bên trái. Thư viện tự đóng khi chọn
  file; các bộ lọc nâng cao nằm trong **Bộ lọc & sắp xếp**.
- **Upload bản vẽ**: kéo thả/chọn nhiều file, xem hàng đợi và thử lại file lỗi.
  Upload vẫn tiếp tục khi chuyển sang xem bản vẽ hoặc tab khác.
- **Trạng thái & tiến độ**: quản lý trạng thái từng trang, tiến độ, thumbnail,
  lọc bản vẽ theo tiến độ, cùng thông tin nhóm/tag. Bấm **Xem bản vẽ** để quay
  lại trang đang chọn.

Chuyển tab giữ bản vẽ, trang đang chọn và mức zoom. Có thể dùng phím mũi tên,
Home/End khi focus các tab để chuyển chế độ.

## Tiến độ, nhóm và upload nhiều file

- Kéo thả hoặc chọn nhiều PDF/PNG/JPG/JPEG trong **Data → Upload bản vẽ**,
  tối đa 100 MB mỗi file. Hàng đợi tải lần lượt, hiển thị phần trăm truyền file rồi **Đang xử lý
  bản vẽ…**. File lỗi có nút **Thử lại**; file đã thành công không bị tải lại.
  Hàng đợi tiếp tục khi chuyển tab, nhưng không giữ các file chờ khi reload
  trình duyệt. File sai định dạng/quá lớn cần chọn file khác.
- Chọn bản vẽ rồi mở **Trạng thái & tiến độ** để xem thumbnail từng trang,
  lọc theo trạng thái và dùng **Đến trang chưa hoàn tất**. Thumbnail tải theo
  từng nhóm 12 trang; PDF được render
  riêng ở kích thước nhỏ, không làm thay đổi tọa độ gán nhãn.
- Mỗi trang có trạng thái **Chưa làm / Đang làm / Chờ kiểm tra / Hoàn tất**.
  Đổi trạng thái tại **Data → Trạng thái & tiến độ** hoặc Generate data.
  Trong Generate data cần lưu nhãn trước khi đổi trạng thái. Trang đã kiểm
  tra không có symbol/text vẫn có thể
  đánh dấu Hoàn tất. Tiến độ `8/20 trang hoàn tất` chỉ đếm trạng thái Hoàn tất,
  độc lập với bộ lọc Đã gán nhãn.
- Nhãn cũ đã lưu được xem là Đang làm. Lưu nội dung gán nhãn đã thay đổi đưa
  trang về Đang làm để kiểm tra lại; lưu cùng nội dung giữ trạng thái hiện có,
  kể cả lần lưu nhãn rỗng đầu tiên cho trang đã hoàn tất.
- Mở **Nhóm và tag** để nhập/chọn dự án, bộ bản vẽ và tag cách nhau bằng dấu
  phẩy. Chọn **Nhóm theo dự án** hoặc **Nhóm theo dự án / bộ bản vẽ** để gom
  danh sách dưới từng tiêu đề nhóm. Tìm kiếm cả tên/nhóm/tag, lọc theo từng trường hoặc tiến độ; sắp xếp
  theo cập nhật gần nhất (mặc định), upload mới nhất hoặc tên A–Z. Ngày cập nhật
  tính cả sửa nhóm/tag, lưu nhãn và đổi trạng thái trang.

Nhóm, tag và trạng thái lưu trong metadata PostgreSQL hiện có, không cần bảng
mới. Trạng thái dùng revision của workflow và nhãn để từ chối cập nhật từ
phiên cũ; giao diện tải lại thông tin khi gặp xung đột.

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
| PATCH | `/api/v1/documents/{id}` | Set `project`, `drawing_set`, `tags` |
| PUT | `/api/v1/documents/{id}/pages/{page}/status` | Set status with workflow `revision` and `annotation_revision` |
| GET | `/api/v1/documents/{id}/pages/{page}/thumbnail.jpg` | Small cached page thumbnail |
| GET | `/api/v1/documents/{id}/original` | Download original bytes from MinIO |
| GET | `/api/v1/documents/{id}/pages/{page}` | Page dimensions and preview/tile links |
| DELETE | `/api/v1/documents/{id}` | Delete original, metadata, annotations and cached artifacts |

Deletion is blocked while a pipeline job is queued/running. Storage failures
return HTTP 503; an unsuccessful MinIO deletion retains the catalog entry so the
user can retry. Uploads clean up the object if the database insert fails.

Verify a running stack with `python scripts/smoke_data.py`. The script uploads its
own two-page PDF, saves OCR labels, checks filtering/download/export, then deletes
its test drawing.

Workflow/API regressions: `PYTHONPATH=src:tests python -m unittest test_web_main
test_annotations test_data_management -v`. Add `DOCUMENT_TEST_STORAGE=1` and
`test_document_storage` with PostgreSQL/MinIO settings to exercise real storage
in disposable schemas/buckets.
