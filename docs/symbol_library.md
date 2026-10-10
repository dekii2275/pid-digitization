# Kho symbol chuẩn

Web mặc định chạy `app.web_main` và lưu danh mục symbol trong PostgreSQL của
service `db` (database `pid_db` theo cấu hình mặc định). PostgreSQL khởi động
cùng frontend và backend; dữ liệu nằm trong Docker volume `postgres_data`.
Backend nhận `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`,
`POSTGRES_PASSWORD`, `POSTGRES_DB` từ Compose. File gốc và ảnh xem trước được
lưu trực tiếp vào PostgreSQL dưới dạng `BYTEA`.

## Thiết kế dữ liệu

| Bảng | Vai trò |
| --- | --- |
| `symbol_definitions` | Mã duy nhất, tên chuẩn, nhóm, trạng thái bật/tắt, nguồn, thời gian tạo/sửa và vùng xem trước nếu dùng ảnh tham chiếu chung. |
| `symbol_assets` | Một file gốc và một ảnh xem trước cho mỗi symbol; lưu tên gốc, MIME, SHA-256, kích thước và nội dung file. Khóa ngoại có `ON DELETE CASCADE`. |
| `symbol_library_state` | Ghi nhận lần chuyển dữ liệu SQLite và lần seed, tránh nhập lại symbol đã bị xóa sau khi khởi động. |

Các bảng được tạo trong một giao dịch khi backend khởi động. Nếu thấy kho
SQLite cũ ở `uploads/symbol-library/symbols.sqlite3`, hệ thống sao chép từng
symbol và từng file sau khi kiểm tra kích thước/SHA-256. File SQLite và thư mục
asset cũ được giữ nguyên để đối chiếu; các lần chạy tiếp theo dùng PostgreSQL.
Nếu không có dữ liệu cũ, kho ban đầu gồm đúng hai symbol chuẩn từ
`src/app/seed_symbols`. 203 label suy đoán từ `label_symbol` không được nạp.

## Import, sửa và xóa trên web

Mở tab **Nhãn symbol**, nhập mã, tên, nhóm, chọn file gốc và ảnh xem trước rồi
nhấn **Import vào kho**. Mỗi lần nhập một symbol; mã trùng bị từ chối. File gốc
hỗ trợ DWG, DXF, PNG, JPG, WEBP, BMP, TIFF, PDF (tối đa 20 MB). Ảnh xem trước
hỗ trợ PNG, JPG, WEBP (tối đa 5 MB) và được kiểm tra định dạng thực. Có thể
sửa tên/nhóm, bật/tắt hoặc xóa symbol trong cùng màn hình. Xóa cần xác nhận và
xóa cả hai file khỏi PostgreSQL; symbol đã xóa không xuất hiện lại sau restart.
Bản vẽ đã lưu vẫn giữ các đối tượng được thêm trước đó.

API: `GET /api/v1/symbol-library`, `POST /api/v1/symbol-library/import`,
`PATCH /api/v1/symbol-library/{code}`, `DELETE /api/v1/symbol-library/{code}`
và `GET /api/v1/symbol-library/{code}/{source|preview}`. Editor chỉ hiển thị
symbol đang bật trong kho.

Chạy kiểm thử tích hợp với `SYMBOL_TEST_DATABASE=1`; mỗi bài kiểm thử tạo một
schema PostgreSQL tạm rồi xóa schema đó khi hoàn tất.
