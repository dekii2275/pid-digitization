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

Mở **Nhãn symbol**, chọn tab **Tạo nhãn mới**, nhập mã, tên, nhóm, chọn một ảnh gốc symbol rồi
nhấn **Tạo nhãn mới**. Tab **Quản lý nhãn** chứa danh sách, tìm kiếm, lọc nhóm,
xem chi tiết và thao tác chỉnh sửa/bật/tắt/xóa. Hai tab thay thanh công cụ bản vẽ
khi đang ở phần Nhãn symbol. Nội dung form và bộ lọc được giữ khi chuyển qua lại
giữa hai tab. Form chỉ có một ô tải ảnh và không hiển thị xem trước
khi chọn file. Mỗi lần nhập một symbol; mã trùng bị từ chối. Ảnh gốc hỗ trợ
PNG, JPG, WEBP, BMP, TIFF (tối đa 20 MB, mỗi chiều ít nhất 8 pixel, tối đa
25 triệu pixel) và được kiểm tra định dạng thực. Backend giữ nguyên file gốc,
tự tạo ảnh PNG tối đa 512 × 512 pixel để hiển thị trong kho và editor.
API vẫn hỗ trợ nhập DWG, DXF, PDF kèm trường `preview` riêng (PNG, JPG, WEBP,
tối đa 5 MB) cho các client cũ. Có thể
sửa tên/nhóm, bật/tắt hoặc xóa symbol trong cùng màn hình. Xóa cần xác nhận và
xóa cả hai file khỏi PostgreSQL; symbol đã xóa không xuất hiện lại sau restart.
Bản vẽ đã lưu vẫn giữ các đối tượng được thêm trước đó.

Bấm vào ảnh, mã hoặc tên symbol trong danh sách để mở popup chi tiết gồm
ảnh xem trước, mã, tên, nhóm, trạng thái, nguồn, ngày tạo và lần cập nhật cuối
(giờ Việt Nam), cùng liên kết tải file gốc. Đóng popup bằng nút Đóng, dấu X,
phím Escape hoặc bấm ra ngoài popup.

API: `GET /api/v1/symbol-library`, `POST /api/v1/symbol-library/import`,
`PATCH /api/v1/symbol-library/{code}`, `DELETE /api/v1/symbol-library/{code}`
và `GET /api/v1/symbol-library/{code}/{source|preview}`. Editor chỉ hiển thị
symbol đang bật trong kho.

Chạy kiểm thử tích hợp với `SYMBOL_TEST_DATABASE=1`; mỗi bài kiểm thử tạo một
schema PostgreSQL tạm rồi xóa schema đó khi hoàn tất.
