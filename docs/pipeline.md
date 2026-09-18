Bài toán chúng ta cần hướng đến không chỉ là OCR hay nhận diện hình ảnh, mà là:

> **Tự động chuyển bản vẽ P&ID/PFD dạng ảnh thành một mô hình dữ liệu kỹ thuật có cấu trúc, trong đó biết được thiết bị nào tồn tại, chúng được gắn nhãn gì, nối với thành phần nào và dòng chảy đi theo hướng nào.**

## Pipeline mục tiêu

```text
Ảnh/PDF P&ID
    ↓
Phát hiện symbol, thiết bị, van, instrument
    ↓
Nhận diện text và tag ID
    ↓
Phát hiện pipe, signal line, arrow
    ↓
Khôi phục topology và quan hệ kết nối
    ↓
Gán ngữ nghĩa kỹ thuật
    ↓
Graph/Digital P&ID/DEXPI
```

## Hệ thống cần trả lời được

Ví dụ từ một bản vẽ, hệ thống phải biết:

- Có những thiết bị nào?
- Tag của từng thiết bị là gì?
- Van hoặc instrument nào thuộc thiết bị nào?
- Đường ống nào nối giữa hai thiết bị?
- Đâu là điểm T, điểm giao hoặc connector?
- Dòng chảy đi từ đâu đến đâu?
- Line đó là piping line hay signal line?
- Một thiết bị có input/output nào?
- Có thành phần nào bị thiếu, không nối hoặc nhận diện với độ tin cậy thấp không?

## Đầu ra mong muốn

### 1. Kết quả nhận diện

```json
{
  "type": "pump",
  "tag": "P-101",
  "bbox": [120, 240, 180, 310],
  "confidence": 0.96
}
```

### 2. Graph kết nối

```text
Tank T-101
   ↓ connected_by
Pipe L-101
   ↓ connected_to
Pump P-101
   ↓ connected_by
Pipe L-102
   ↓
Valve V-101
```

### 3. Digital P&ID

Mỗi node cần có:

- loại thiết bị;
- tag/name;
- tọa độ trên bản vẽ;
- thuộc tính kỹ thuật nếu lấy được;
- đường dẫn tới ảnh gốc;
- confidence;
- thông tin kiểm duyệt/chỉnh sửa.

Mỗi edge cần có:

- loại quan hệ;
- node đầu và node cuối;
- loại line;
- hướng dòng;
- confidence;
- nguồn phát hiện.

## Điểm khó nhất

Phần khó nhất không phải nhận diện từng symbol riêng lẻ, mà là **khôi phục đúng topology**.

Ví dụ:

```text
Nhìn thấy 3 line giao nhau
```

chưa đủ để kết luận chúng được nối với nhau. Hệ thống phải phân biệt:

- giao nhau nhưng không kết nối;
- kết nối dạng T;
- kết nối dạng cross;
- line bị ngắt do text hoặc symbol che mất;
- arrow nằm giữa line;
- hai line gần nhau nhưng thuộc hai hệ thống khác nhau.

Vì vậy, mục tiêu cốt lõi là:

```text
visual recognition
        +
spatial reasoning
        +
engineering rules
        =
semantic P&ID graph
```

## Phạm vi nên chia thành hai mức

### MVP

MVP nên tập trung vào:

- Nhận ảnh P&ID.
- Nhận diện nhóm symbol chính.
- OCR text/tag.
- Phát hiện line.
- Nối symbol và line.
- Xuất JSON và lưu PostgreSQL.
- Cho phép người dùng sửa kết quả sai.
- Chạy hoàn toàn local, không phụ thuộc Azure.

### MVP đã thống nhất và thứ tự triển khai

MVP sẽ được triển khai dưới dạng một pipeline tối thiểu chạy được từ đầu đến cuối:

```text
1 ảnh/PDF P&ID
    ↓
Phát hiện symbol chính: thiết bị, van, instrument
    ↓
OCR text và tag ID, ví dụ P-101 hoặc V-101
    ↓
Phát hiện pipe/line
    ↓
Nối symbol với line
    ↓
Xuất graph dưới dạng JSON
    ↓
Người dùng kiểm tra và chỉnh sửa kết quả
```

Tiêu chí hoàn thành MVP:

- Chạy được hoàn toàn local trên một ảnh P&ID.
- Nhận diện được một nhóm symbol chính với bounding box và confidence.
- Trích xuất được text/tag và liên kết tag với symbol tương ứng.
- Phát hiện được các line chính và quan hệ kết nối cơ bản.
- Xuất được JSON có node, edge, tọa độ, confidence và nguồn phát hiện.
- Có cơ chế để người dùng xem, sửa và lưu lại kết quả.

### Công việc đầu tiên

Công việc đầu tiên là **chuẩn bị một bộ dữ liệu P&ID mẫu có annotation** để làm đầu vào thống nhất cho toàn bộ pipeline. Mỗi ảnh cần được đánh dấu tối thiểu:

- bounding box và loại của thiết bị, van, instrument;
- text/tag tương ứng với từng symbol;
- đường pipe/line;
- các quan hệ kết nối cơ bản giữa symbol và line.

Sau khi có bộ dữ liệu mẫu, cần định nghĩa schema JSON đầu ra và xây dựng vertical slice đầu tiên:

```text
1 ảnh P&ID → symbol + tag + line → graph JSON
```

Chưa đưa DEXPI, mô hình 3D, mô phỏng quy trình hoặc suy luận dòng chảy nâng cao vào giai đoạn này.

### Phiên bản đầy đủ

Sau đó mở rộng thêm:

- Nhận diện nhiều loại symbol hơn.
- Phân biệt piping/signal line.
- Nhận diện tee/cross fitting.
- Suy luận hướng dòng chảy.
- Xử lý line bị đứt hoặc bị che.
- Kiểm tra cycle và kết nối bất hợp lý.
- Xuất mô hình DEXPI.
- Hỗ trợ nhiều trang P&ID.
- Hỗ trợ retraining theo từng doanh nghiệp/dự án.

## Những gì không nên coi là mục tiêu ban đầu

Ban đầu không nên cố giải quyết ngay:

- dựng mô hình 3D nhà máy;
- mô phỏng quy trình hóa học;
- tự thiết kế hoặc sửa lại P&ID;
- trích xuất toàn bộ thông số kỹ thuật thủ công;
- đạt độ chính xác tuyệt đối mà không cần human review.

## Phát biểu bài toán đề xuất

Có thể dùng phát biểu sau làm mục tiêu dự án:

> Xây dựng một hệ thống self-hosted sử dụng computer vision, OCR và các luật topology chuyên ngành để chuyển bản vẽ P&ID/PFD dạng ảnh thành graph kỹ thuật có ngữ nghĩa. Hệ thống phải nhận diện được các thành phần chính, liên kết text với thiết bị, khôi phục quan hệ kết nối và hướng dòng chảy, cho phép người dùng kiểm duyệt kết quả, sau đó xuất dữ liệu dưới dạng JSON, graph database và Digital P&ID/DEXPI.

Tóm lại, sản phẩm cần hướng tới là một **P&ID digitization platform**, không chỉ là một module object detection.
