# Mở lại, chỉnh sửa và xuất DXF

Mở **Review → Mở bản vẽ đã xử lý**, chọn bản vẽ và trang. Hoặc mở trang trong
**Data** và bấm **Chỉnh sửa / DXF**. Không cần chạy lại AI hoặc giữ job cũ trong
bộ nhớ. Pipeline mới lưu kết quả vào PostgreSQL ngay khi hoàn tất; có thể xử lý
trang đang chọn thay vì chỉ trang đầu.

## Chọn nguồn và sửa

Ứng dụng ưu tiên **Bản chỉnh sửa đã lưu**. Menu nguồn cũng cho phép mở **Kết quả
AI gần nhất** hoặc **Nhãn đã lưu**. Nếu chưa có dữ liệu, có thể thêm thủ công.
Các nguồn AI và nhãn gốc được giữ riêng; chạy lại AI không ghi đè bản đã sửa.

- Chọn symbol/text/line trong danh sách hoặc trên canvas, bấm **Bắt đầu chỉnh sửa**.
- Sửa tag, text, tọa độ, kích thước và góc xoay của symbol; kéo để di chuyển/resize.
- Chọn **Hình CAD** cho symbol: bơm, van cổng, van một chiều, van cầu, đầu nối sang
  bản vẽ khác, instrument, bồn/bình hoặc khung thiết bị. `LC-001` dùng hình đầu nối;
  `VALVES-012`, `VALVES-019`, `VALVES-020` dùng các hình van khác nhau. Hình CAD đã
  chọn trong bản lưu được giữ nguyên; có thể chọn lại trong Review nếu cần.
- Thêm symbol/text bằng kéo vùng; thêm đường ống bằng kéo từ đầu tới cuối. Có thể
  sửa hai đầu đường ống và phân loại đường ống/tín hiệu.
- Có thể thêm và sửa quan hệ kết nối giữa các symbol. Xóa symbol cũng gỡ các quan
  hệ tham chiếu tới nó. Di chuyển symbol chưa tự định tuyến lại đường ống.
- **Undo / Redo** giữ tối đa 50 thao tác trong phiên chỉnh sửa. Một lần kéo được
  tính là một thao tác. Lịch sử Undo không lưu qua reload.
- **Xem vector** hiển thị các hình CAD cơ bản và text thay cho ảnh nền. Bấm **Xem
  ảnh gốc** để đối chiếu với scan/PDF.

**Lưu kết quả** lưu theo bản vẽ/trang với số phiên sửa `version`. Nếu phiên khác
đã lưu trước, ứng dụng báo xung đột và giữ nội dung đang sửa để người dùng xử lý.
Nút **Tải lại bản đã lưu** mở dữ liệu mới nhất, hỏi xác nhận nếu có thay đổi chưa
lưu. Chuyển tab trong ứng dụng giữ nội dung đang sửa; đổi trang/nguồn cần xử lý
thay đổi chưa lưu. Trình duyệt cảnh báo khi đóng/reload trang có thay đổi.

## Xuất DXF

Khai báo **Đơn vị CAD** và **Đơn vị / pixel**, rồi lưu. Mặc định là không đơn vị,
1 pixel = 1 đơn vị CAD. P&ID là sơ đồ; hệ thống không suy ra tỷ lệ vật lý của đường
ống từ ảnh scan. Chọn tỷ lệ theo quy ước bàn giao bản vẽ của đơn vị.

Bấm **Xuất DXF** sau khi lưu. File DXF R2010 chứa:

| Nội dung | Đối tượng / layer |
| --- | --- |
| Thiết bị, van, bơm | Block INSERT / `PID_EQUIPMENT` |
| Instrument | Block INSERT / `PID_INSTRUMENTS` |
| Đầu nối sang bản vẽ khác | Block INSERT / `PID_CONNECTORS`, hiển thị mặc định |
| Tag | Thuộc tính `TAG` gắn vào block / `PID_TAGS` |
| ID đối tượng | Thuộc tính ẩn `EID` và XDATA `VPI_PID` |
| Đường ống | LWPOLYLINE giữ các điểm / `PID_PIPES` |
| Tín hiệu | LWPOLYLINE nét đứt / `PID_SIGNALS` |
| OCR | TEXT hoặc MTEXT / `PID_TEXT` |
| Quan hệ graph | Đường tham khảo nối tâm symbol / `PID_CONNECTIONS`, mặc định tắt |

Tọa độ Y của ảnh được đảo sang hệ tọa độ CAD, tỷ lệ áp dụng cho toàn bộ hình học
và text, góc xoay chuyển đúng chiều. XDATA giữ ID bản vẽ, trang, generation, loại
và ID đối tượng để hỗ trợ tích hợp sau này.

Nét tín hiệu dùng mẫu đứt cơ bản 8 pixel nét / 4 pixel khoảng trống, nhân với tỷ
lệ CAD; mẫu chạy liên tục qua các đỉnh của polyline. Đây không phải bộ linetype
ISA hoặc bộ style gốc của nhà máy. Text có nhiều đoạn xuống dòng chia chiều cao
khung OCR cho các dòng; chế độ vector cũng hiển thị từng dòng.

File xuất dùng **bản chỉnh sửa đã lưu**; cần lưu thay đổi hiện tại trước khi xuất.
Export kiểm tra `version` để tránh tải nhầm nội dung đã bị phiên khác thay đổi.

Symbol hiện là hình cơ bản theo nhóm, chưa tái dựng chính xác mọi ký hiệu hoặc
block riêng của nhà máy. DXF không chứa ảnh nền hoặc mọi nét chưa được nhận diện;
nó chứa các đối tượng đã xử lý và chỉnh sửa. Đây là DXF hình học, chưa phải smart
P&ID native của Plant 3D. File gốc vẫn tải riêng trong Data. Kiểm tra font và hình
symbol trong công cụ CAD đích trước khi bàn giao.

Review hiển thị số symbol, chữ và đường trước khi xuất; dữ liệu không có đường
hoặc OCR được ghi rõ. File vẫn có thể là DXF hợp lệ dù chỉ chứa symbol rời rạc.
Luồng này xuất từ scene ảnh/PDF, chưa nhập hay chuyển nguyên cấu trúc DWG gốc,
không giữ tự động model-space origin, nhiều khung bản vẽ, block và layer của DWG.

## Dữ liệu cũ và lưu trữ

`drawing_review_scenes` bổ sung `version`; `drawing_processed_scenes` giữ kết quả
AI gần nhất của mỗi trang. Cả hai liên kết với bản vẽ, tự dọn khi xóa bản vẽ.
Lưu chỉnh sửa giữ generation và ID của đối tượng để các liên kết hồ sơ thiết bị
còn hợp lệ tiếp tục hoạt động; đổi tag có thể yêu cầu kiểm tra lại liên kết.

Khi khởi động, ứng dụng nhập các artifact cũ còn nằm dưới
`artifacts/pipeline/{drawing_id}/job_*/editor/scene.json` và `final-scene.json`
nếu PostgreSQL chưa có dữ liệu tương ứng. Job cũ không có thông tin trang được
xem là trang 1, theo hành vi pipeline trước đây. Dữ liệu đã có trong PostgreSQL
không bị artifact cũ ghi đè. Nếu cả artifact và bản lưu PostgreSQL đều không còn,
cần chạy lại AI hoặc dùng nhãn đã lưu làm nguồn.

## API và kiểm thử

- `GET /api/v1/documents/{id}/pages/{page}/review-scene?origin=latest`: trả `scene`,
  `version`, `generation`, `origin`, `available_sources`. `origin` có thể là
  `latest`, `review`, `processed`, `annotations`.
- `PUT` cùng đường dẫn: `{version, generation, scene}`; trả 409 khi nguồn hoặc
  phiên sửa đã thay đổi, 422 khi hình học/tham chiếu không hợp lệ.
- `GET .../review-scene/export.dxf?version=N`: tải bản đã lưu đúng phiên sửa.
- `POST /api/v1/documents/{id}/run-all?page_number=N`: xử lý đúng trang.

Cài `src/requirements.cad.txt` bên cạnh các dependency web/storage khi chạy local.
Docker cài ezdxf qua layer riêng.

```sh
DOCUMENT_TEST_STORAGE=1 PYTHONPATH=src:tests python -m unittest test_drawing_editor -v
```

Tests dùng schema/bucket tạm, kiểm tra lưu/mở lại, nhiều trang, xung đột, giữ nguồn
AI/nhãn và nhập artifact cũ. DXF được đọc lại bằng ezdxf, chạy audit và kiểm tra
block/attribute, tọa độ, góc xoay, Unicode, polyline và layer. Kiểm tra tự động
này không thay thế nghiệm thu trong phần mềm CAD mà nhà máy sử dụng.
