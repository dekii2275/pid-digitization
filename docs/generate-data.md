# Gán nhãn dữ liệu trong Generate data

Tab **Generate data** thay cho Editor. Thanh công cụ bản vẽ cũ được ẩn khi mở
màn hình này. Có ba chế độ dùng chung ảnh và dữ liệu:

- **Detect symbol**: chọn nhãn từ thư viện, khoanh hộp chữ nhật quanh symbol.
- **Detect text OCR**: khoanh vùng chữ rồi nhập nguyên văn nội dung.
- **Detect quan hệ**: nối hai symbol hoặc liên kết OCR với một symbol.

Đây là công cụ gán nhãn thủ công để tạo dữ liệu huấn luyện; không cần chạy
pipeline AI. Kết quả Review/pipeline được giữ riêng.

## Symbol

1. Tải PNG/JPG/PDF, hoặc chọn một bản vẽ đã tải. Với PDF, chọn trang cần làm.
2. Tìm mã/tên hoặc lọc nhóm trong thư viện, rồi chọn một nhãn.
3. Kéo trên ảnh để khoanh vùng. Có thể tiếp tục khoanh nhiều symbol cùng nhãn.
4. Chọn **Chọn / sửa**, bấm vào vùng để kéo vị trí hoặc kéo các góc để đổi kích
   thước. Có thể sửa nhãn và tọa độ/kích thước trong phần Thông tin vùng chọn.
5. Bấm **Lưu nhãn** hoặc **Xuất dataset**. Xuất sẽ lưu trước rồi tải ZIP.

Lăn chuột để zoom; kéo nền hoặc chọn **Di chuyển ảnh** để pan. Các thao tác
luôn dùng tọa độ pixel của ảnh gốc, không dùng tọa độ ảnh thu nhỏ trên màn hình.
**Hoàn tác/Làm lại** giữ tối đa 50 thao tác; Ctrl/Cmd+Z để hoàn tác,
Ctrl/Cmd+Shift+Z để làm lại, Delete để xóa vùng chọn, Esc để hủy khoanh.
Xóa một vùng đồng thời xóa các quan hệ tham chiếu vùng đó.

## OCR và quan hệ

Trong chế độ OCR, khoanh vùng rồi nhập nội dung vào ô **Nội dung OCR**.
Hộp OCR có thể di chuyển, sửa tọa độ và đổi kích thước bằng góc dưới bên phải.

Trong chế độ quan hệ, chọn loại quan hệ, đối tượng nguồn và đích rồi bấm
**Thêm quan hệ**. Cũng có thể bấm vào các vùng trên ảnh để chọn hai đầu.
`connected_to` và `flow_to` nối symbol với symbol;
`text_of` nối vùng OCR (nguồn) với symbol (đích). Quan hệ được vẽ trên ảnh và
có thể chọn/xóa trong danh sách. Nội dung OCR có thể để trống khi chỉ cần dữ
liệu phát hiện vùng text; nhập nội dung để dùng cho nhận dạng chữ.

## Lưu và khôi phục

Nhãn lưu trên máy chủ trong `uploads/annotations/<drawing-id>/page-N.json`,
độc lập từng bản vẽ và trang. Metadata bản vẽ mới cũng được lưu trong uploads
để có thể mở lại sau khi backend restart. Các upload cũ chưa có metadata cần
được tải lại một lần. Dữ liệu ảnh vẫn nằm trong thư mục uploads hiện có.

Bản nháp tự lưu ở bộ nhớ trình duyệt và được giữ khi chuyển tab. Khi mở lại,
bản nháp cùng revision được khôi phục. Nhãn máy chủ dùng revision để từ chối
việc ghi đè một phiên đã được lưu bởi cửa sổ khác. **Tải bản máy chủ** mở bản
mới nhất và giữ bản trước trong lịch sử hoàn tác/bản sao cục bộ.

## Dữ liệu xuất

ZIP chứa:

- `images/<drawing-id>-pN.png`: toàn bộ ảnh trang ở đúng kích thước gán nhãn.
- `labels/<drawing-id>-pN.txt`: các hộp symbol theo YOLO
  `class_id center_x center_y width height`, chuẩn hóa về [0,1].
- `classes.txt`, `classes.json`: mã, tên, nhóm và ID lớp.
- `data.yaml`: danh sách lớp và đường dẫn images; cần tạo bộ validation riêng.
- `annotations/<drawing-id>-pN.json`: tọa độ pixel, symbol, OCR, quan hệ và nguồn.

ID lớp được giữ trong `uploads/annotations/classes.json`, dùng chung tất cả
bản vẽ/trang và chỉ thêm ở cuối khi thư viện có nhãn mới. Đổi tên, tắt hoặc xóa
nhãn thư viện không đổi ID của dữ liệu đã gán nhãn. YOLO chỉ xuất hộp symbol;
OCR và quan hệ giữ trong JSON. Mỗi ZIP chứa một trang, chưa tự chia train/val
và chưa chạy huấn luyện.

## API và kiểm tra

- `GET /api/v1/documents`: bản vẽ hiện có và metadata được lưu.
- `GET /api/v1/documents/{id}/pages/{page}`: kích thước/tile của từng trang.
- `GET/PUT /api/v1/documents/{id}/pages/{page}/annotations`.
- `GET /api/v1/documents/{id}/pages/{page}/annotations/export`: ZIP sau khi lưu.

Server kiểm tra tọa độ hữu hạn, hộp nằm trong ảnh, mã lớp tồn tại, ID khác
nhau và quan hệ có hai đầu hợp lệ. Revision cũ trả 409; dữ liệu sai trả 422.
Kiểm tra API bằng `python -m unittest discover -s tests -p 'test_annotations.py' -v`
với `PYTHONPATH=src`; các test dùng thư mục tạm và thư viện giả lập.
