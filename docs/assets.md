# Thiết bị, tra cứu tag và hồ sơ

Mở tab **Thiết bị** hoặc nút **Find tag**. Hệ thống tìm tag trên toàn bộ dự án,
mở đúng trang, phóng tới vị trí và đánh dấu khung vàng. Có hai chế độ:

- **Tag / mã symbol**: tìm một phần tag hoặc mã loại symbol (ví dụ `VALVES-019`),
  không phân biệt hoa/thường; lọc dự án; bao gồm nhãn symbol, OCR và review đã lưu.
  Tìm mã loại vẫn trả về symbol đã có tag riêng. Chọn kết quả để mở đúng vị trí.
  Symbol chưa có tag được ghi rõ; có thể chọn vị trí và liên kết thủ công vào hồ sơ.
- **Hồ sơ thiết bị**: tìm theo tag, tên, loại hoặc khu vực; xem cả thiết bị chưa
  có liên kết bản vẽ. Kết quả chia trang, 50 mục mỗi trang.

## Chuẩn bị dữ liệu

1. Trong **Data → Nhóm và tag**, khai báo dự án, số bản vẽ, revision và trạng thái
   **Đang sử dụng / Đã thay thế**. Bản vẽ cũ mặc định là Đang sử dụng; kỹ sư cần
   kiểm tra và khai báo đúng trạng thái. Chưa có quy trình phê duyệt revision hoặc
   tự động chọn revision mới nhất.
2. Lưu OCR trong **Generate data**. Nếu tạo quan hệ `text_of` từ OCR tới symbol,
   kết quả tìm kiếm sẽ đưa tới symbol; OCR chưa liên kết vẫn tìm được và được ghi rõ.
3. Với pipeline AI, nhập/kiểm tra tag trong **Review**, rồi bấm lưu review. Kết quả
   review mới được lưu bền vững trong PostgreSQL, độc lập với danh sách job trong
   bộ nhớ. Có thể mở lại và sửa từng trang trong **Review** hoặc qua **Data →
   Chỉnh sửa / DXF**. Các artifact cũ còn trên máy được nhập khi khởi động nếu
   chưa có bản lưu trong PostgreSQL; xem [trình chỉnh sửa](drawing-editor.md).

## Hồ sơ và liên kết

Chọn tag để tạo hồ sơ mới hoặc tìm hồ sơ hiện có và gắn vị trí vào đó. Có thể tạo
hồ sơ độc lập bằng **Tạo hồ sơ**, sau đó mở hồ sơ → **Liên kết bản vẽ** → tìm mã
symbol hoặc tag → chọn vị trí → **Xác nhận liên kết**. Chọn hồ sơ đã có vị trí sẽ
tự mở vị trí đầu tiên; các vị trí khác nằm trong danh sách bên phải.

Khi tạo hồ sơ từ một vị trí, **Liên kết với vị trí đang chọn** được bật sẵn và có
thể bỏ chọn để lưu độc lập. Symbol chưa có tag và bản vẽ chưa có dự án vẫn hỗ trợ
liên kết thủ công theo đúng ID symbol và mã loại. Dự án bản vẽ đã khai báo phải
trùng dự án hồ sơ. Liên kết không tự sửa tag hay dự án trên bản vẽ; không tự động
gộp các symbol cùng mã loại hay cùng tag. Một hồ sơ có thể có nhiều vị trí.

Sau khi liên kết, có thể tìm vị trí bằng tag hồ sơ, kể cả khi symbol chưa có tag
nguồn. Kết quả giữ riêng `tag` nguồn và `asset_tag` của hồ sơ.

Tag là duy nhất trong phạm vi dự án và khu vực, sau khi chuẩn hóa hoa/thường,
khoảng trắng và dấu gạch ngang Unicode. Hai khu vực hoặc dự án có thể có cùng tag.
Sửa tag hồ sơ không sửa OCR trên bản vẽ. Chỉnh sửa hồ sơ kiểm tra `version` để từ
chối ghi đè từ phiên cũ.

Nếu tag hoặc dự án nguồn đổi, symbol bị xóa hoặc review được thay bằng một run
mới, liên kết không còn khớp được đưa vào **cần kiểm tra lại**. Kỹ sư có thể gỡ
và gắn lại từ kết quả mới. Thay đổi vị trí box với cùng ID/tag vẫn giữ liên kết.
Xóa bản vẽ gỡ các vị trí liên quan, giữ hồ sơ thiết bị và tài liệu.

## Tài liệu

Mỗi hồ sơ có nhóm Datasheet, Hướng dẫn, Ảnh hiện trường, Kiểm định, Bảo trì, Khác.
Có thể upload PDF/ảnh/Word/Excel/CSV/TXT tối đa **20 MB mỗi tệp**, hoặc thêm đường
dẫn HTTP/HTTPS tới kho tài liệu nội bộ. Hệ thống không tải nội dung từ URL này.
Tệp upload lưu trong bucket MinIO hiện có, metadata và SHA-256 trong PostgreSQL.
Download dùng API, không đưa thông tin đăng nhập MinIO ra trình duyệt. Xóa tài
liệu có bước xác nhận tại chỗ. Sao lưu cả PostgreSQL và MinIO như bản vẽ.

## API

| Method | Path | Mục đích |
| --- | --- | --- |
| GET | `/api/v1/asset-search?q=&project=&include_superseded=false&offset=0&limit=50` | Tra cứu vị trí tag |
| GET, POST | `/api/v1/assets` | Tìm hồ sơ / tạo hồ sơ, có thể kèm `occurrence` |
| GET, PUT | `/api/v1/assets/{id}` | Hồ sơ, vị trí, tài liệu / cập nhật với `version` |
| POST | `/api/v1/assets/{id}/occurrences` | Gắn vị trí từ kết quả tra cứu |
| DELETE | `/api/v1/assets/{id}/occurrences/{link_id}` | Gỡ liên kết |
| POST | `/api/v1/assets/{id}/documents/links` | Thêm đường dẫn |
| POST | `/api/v1/assets/{id}/documents/upload` | Multipart: `file`, `title`, `category` |
| GET | `/api/v1/assets/{id}/documents/{document_id}/download` | Tải tệp |
| DELETE | `/api/v1/assets/{id}/documents/{document_id}` | Xóa tài liệu |

`occurrence` gồm `drawing_id`, `page_number`, `source` (`annotation`/`review`),
`kind` (`symbol`/`text`), `item_id`, `generation`, `tag`, `symbol_code` (mã loại).
`tag` có thể rỗng với symbol có `symbol_code` khớp bản lưu. Server xác minh lại vị trí
và tag trước khi gắn; không nhận box tùy ý từ client. Kết quả có `review_status`,
`revision_label`, `lifecycle`, `box`, `symbol_code`, `asset_id` và `link_id` nếu đã liên kết.
`tag` rỗng khi symbol chỉ có mã loại; mã loại không được dùng thay tag thiết bị.
Kết quả có thêm `asset_tag` và `asset_project` khi vị trí được liên kết.

Các bảng `plant_assets`, `plant_asset_occurrences`, `plant_asset_documents` và
`drawing_review_scenes` được khởi tạo bổ sung, không xóa dữ liệu hiện có. Tìm kiếm
hiện đọc nhãn lưu trực tiếp để tránh chỉ mục lỗi thời; nên bổ sung chỉ mục tìm
kiếm khi mở rộng ra kho bản vẽ lớn, sau khi đo tải pilot.

## Kiểm thử

```sh
PYTHONPATH=src:tests python -m unittest test_assets.TestOccurrenceExtraction test_data_management -v
DOCUMENT_TEST_STORAGE=1 PYTHONPATH=src:tests python -m unittest test_assets.TestAssetCatalog -v
cd frontend && node --test tests/assets.test.mjs
```

Integration tests dùng schema PostgreSQL và bucket MinIO tạm, tự dọn sau khi chạy.
