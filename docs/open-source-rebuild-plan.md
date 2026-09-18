# Kế hoạch rebuild P&ID digitization bằng các thành phần open-source

## 1. Mục tiêu

Rebuild hệ thống theo hướng self-hosted/offline, loại bỏ các phụ thuộc runtime vào Azure nhưng vẫn giữ lại các thuật toán xử lý ảnh, phát hiện đường ống và xây dựng graph đang có.

Pipeline mục tiêu:

```text
Ảnh P&ID
  -> tiền xử lý ảnh
  -> nhận diện symbol local
  -> OCR local
  -> phát hiện line/arrow
  -> xây dựng topology graph
  -> lưu trữ và xuất dữ liệu
```

Lưu ý: self-hosted không có nghĩa là không có dependency. Vẫn cần cài thư viện, system package và tải hoặc tự huấn luyện model weights trước khi chạy.

## 2. Phân loại dependency hiện tại

### 2.1. Dependency Azure bắt buộc phải thay

| Chức năng | Dependency hiện tại | Mức độ thay đổi |
|---|---|---|
| Nhận diện symbol | Azure ML endpoint, bearer token | Cao |
| OCR | Azure AI Document Intelligence/Form Recognizer | Trung bình |
| Lưu ảnh và request | Azure Blob Storage | Trung bình |
| Graph persistence | Azure SQL/SQL Server Graph, Azure AD, `pyodbc` | Cao |
| Cấu hình và khởi động service | `DefaultAzureCredential`, Azure connection settings | Trung bình |

### 2.2. Thành phần có thể giữ lại

Các thành phần sau không phụ thuộc trực tiếp vào Azure và có thể tiếp tục sử dụng:

- OpenCV và các bước tiền xử lý ảnh.
- Hough transform và line detection hiện tại.
- Shapely cho xử lý hình học.
- NetworkX cho xây dựng graph trung gian.
- Logic tương quan giữa text và symbol.
- Logic kết nối line, symbol, arrow trong graph construction.
- FastAPI, Pydantic và Prometheus metrics.
- Các unit test hiện có, sau khi cập nhật mock và contract của các adapter.

## 3. Thay thế nhận diện symbol

### Hiện trạng

[`symbol_detection_endpoint_client.py`](../src/app/services/symbol_detection/symbol_detection_endpoint_client.py) gửi ảnh tới endpoint `/score` và dùng bearer token. Repository không chứa đầy đủ model weights để chạy detector độc lập.

### Thiết kế mới

Tạo một interface chung:

```text
SymbolDetector
  -> LocalSymbolDetector
```

`LocalSymbolDetector` sẽ:

1. Load model một lần khi service khởi động.
2. Nhận ảnh hoặc mảng OpenCV.
3. Trả về cùng định dạng bounding box, class label và confidence như service hiện tại.
4. Cho phép chọn `cpu` hoặc `cuda` qua configuration.

Có thể dùng [MMDetection](https://github.com/open-mmlab/mmdetection), một framework object detection mã nguồn mở với giấy phép Apache 2.0. Cũng có thể triển khai lại kiến trúc detector trong paper nếu có dataset và weights phù hợp.

### File cần chỉnh

- [`src/app/services/symbol_detection/symbol_detection_endpoint_client.py`](../src/app/services/symbol_detection/symbol_detection_endpoint_client.py): thay bằng local detector hoặc đổi thành adapter interface.
- [`src/app/services/symbol_detection/symbol_detection_service.py`](../src/app/services/symbol_detection/symbol_detection_service.py): giữ logic hậu xử lý, chỉ thay dependency của client.
- [`src/app/services/request_session_builder.py`](../src/app/services/request_session_builder.py): có thể xóa nếu detector chạy trực tiếp trong process.
- Các test trong `src/_tests_/unit/services/symbol_detection/`: chuyển từ mock HTTP sang mock model inference.

### Rủi ro cần xử lý

Framework open-source không tự cung cấp model P&ID có độ chính xác phù hợp. Cần kiểm tra license của dataset, weights và nhãn symbol trước khi dùng cho sản phẩm thương mại.

## 4. Thay Azure OCR

### Hiện trạng

[`ocr_client.py`](../src/app/services/text_detection/utils/ocr_client.py) tạo `DocumentAnalysisClient`, gọi model `prebuilt-read` và chuyển polygon text về cho `text_detection_service.py`.

### Phương án khuyến nghị

Tạo interface:

```text
OcrEngine
  -> PaddleOcrEngine
```

PaddleOCR có pipeline text detection và text recognition, đồng thời hỗ trợ chỉ định model local. Xem [tài liệu OCR pipeline của PaddleOCR](https://www.paddleocr.ai/main/en/version3.x/pipeline_usage/OCR.html).

Nếu cần bám sát phương pháp trong paper, dùng:

```text
CRAFT       -> phát hiện vùng text
Tesseract   -> nhận dạng ký tự
```

Tesseract có giấy phép Apache 2.0 và phù hợp làm recognition engine local. Xem [repository Tesseract](https://github.com/tesseract-ocr/tesseract).

### Contract nên giữ nguyên

Adapter OCR mới nên trả về tối thiểu:

```text
text/content
polygon hoặc bounding box
confidence nếu engine cung cấp
```

Giữ contract này giúp phần [`text_detection_service.py`](../src/app/services/text_detection/text_detection_service.py) và [`symbol_to_text_correlation_service.py`](../src/app/services/text_detection/symbol_to_text_correlation_service.py) ít phải thay đổi.

### File cần chỉnh

- [`src/app/services/text_detection/utils/ocr_client.py`](../src/app/services/text_detection/utils/ocr_client.py): bỏ Azure client, gọi engine local.
- `src/app/services/text_detection/text_detection_service.py`: chỉ chỉnh nếu format polygon/confidence khác.
- `src/_tests_/unit/services/text_detection/utils/test_ocr_client.py`: thay mock response của Azure bằng mock response local.
- Có thể giữ [`text_detection_image_preprocessor.py`](../src/app/services/text_detection/utils/text_detection_image_preprocessor.py).

## 5. Thay Azure Blob Storage

### Hiện trạng

[`blob_storage_client.py`](../src/app/services/blob_storage_client.py) dùng `BlobServiceClient`, `ContainerClient` và `DefaultAzureCredential`. Middleware cũng lưu input request vào Blob Storage để tracing.

### Thiết kế mới

Tách storage thành interface:

```text
StorageBackend
  -> LocalStorageBackend       # MVP, lưu vào thư mục data/
  -> S3CompatibleBackend       # production nếu cần object storage
```

MVP nên dùng filesystem local:

```text
data/
  inputs/
  outputs/
  debug/
```

Nếu cần lưu trữ phân tán, có thể dùng SeaweedFS, một lựa chọn S3-compatible với giấy phép Apache 2.0. Xem [SeaweedFS](https://github.com/seaweedfs/seaweedfs).

### File cần chỉnh

- [`src/app/services/blob_storage_client.py`](../src/app/services/blob_storage_client.py): chuyển thành `StorageBackend` hoặc giữ tên cũ nhưng dùng filesystem.
- [`src/app/routes/tracing_middleware.py`](../src/app/routes/tracing_middleware.py): lưu file và JSON vào local storage backend.
- [`src/app/routes/controller.py`](../src/app/routes/controller.py): bỏ bước khởi tạo Azure Blob trong lifespan.
- [`src/app/utils/override_imwrite.py`](../src/app/utils/override_imwrite.py): nên loại bỏ monkey patch `cv2.imwrite`; các nơi cần lưu ảnh nên gọi storage backend rõ ràng.
- [`src/app/services/storage_path_template_builder.py`](../src/app/services/storage_path_template_builder.py): có thể giữ lại để tạo key/path thống nhất.
- `src/_tests_/unit/services/test_blob_storage_client.py`: đổi thành test cho local backend.

## 6. Thay Azure SQL Graph

### Hiện trạng

Graph persistence hiện phụ thuộc vào SQL Server Graph và Azure AD. Các SQL script sử dụng những thành phần đặc thù như:

- `AS NODE` và `AS EDGE`.
- `$node_id`.
- `MATCH` của SQL Server Graph.
- Kết nối `pyodbc` và Azure access token.

### Phương án khuyến nghị

Phương án dễ bảo trì nhất là PostgreSQL với bảng node/edge thông thường:

```text
pnid
sheet
asset
symbol
text
line
connection
```

Trong mô hình này, `connection` lưu quan hệ giữa các node. PostgreSQL có giấy phép open source tương đối tự do; xem [PostgreSQL License](https://www.postgresql.org/about/licence/).

Nếu cần truy vấn graph bằng Cypher, dùng Apache AGE, một extension PostgreSQL hỗ trợ graph và openCypher; xem [Apache AGE](https://age.apache.org/overview/).

### File cần chỉnh

- [`src/app/repository/connect.py`](../src/app/repository/connect.py): thay `pyodbc` và Azure token bằng PostgreSQL driver.
- [`src/app/repository/database_repository.py`](../src/app/repository/database_repository.py): viết lại câu lệnh insert/query.
- [`src/app/repository/pnid_graph_db.py`](../src/app/repository/pnid_graph_db.py): thay API SQL Graph bằng schema PostgreSQL hoặc AGE.
- [`src/app/services/graph_persistence/graph_persistence_service.py`](../src/app/services/graph_persistence/graph_persistence_service.py): cố gắng giữ nguyên API `persist()` để không ảnh hưởng graph construction.
- Toàn bộ SQL trong [`src/graph-db-model`](../src/graph-db-model): viết lại DDL cho PostgreSQL/AGE.
- [`docs/design-db.md`](design-db.md): cập nhật schema và cách truy vấn mới.
- Các test trong `src/_tests_/unit/services/graph_persistence/`: thay mock SQL Server bằng PostgreSQL test database hoặc repository mock.

## 7. Queue và job processing

### Hiện trạng

[`queue_consumer.py`](../src/app/queue_consumer.py) dùng queue trong RAM và một worker thread. Thành phần này không phải Azure dependency, có thể giữ cho bản demo.

### Khi triển khai production

Nên chuyển sang:

```text
FastAPI -> Celery task -> RabbitMQ hoặc Redis -> worker
```

Celery phù hợp cho distributed task processing; xem [Celery documentation](https://docs.celeryq.dev/en/main/).

Trạng thái job không nên chỉ lưu trong RAM. Nên lưu ở PostgreSQL hoặc một store bền vững khác.

## 8. Configuration và dependency

### Xóa khỏi dependency chính

Trong [`src/requirements.txt`](../src/requirements.txt), xem xét loại bỏ:

```text
azure-storage-blob
azure-identity
azure-ai-formrecognizer
pyodbc
```

### Dependency thay thế dự kiến

```text
torch + mmdetection                 # local symbol detector
paddleocr + paddlepaddle            # hoặc pytesseract + Tesseract
psycopg hoặc sqlalchemy              # PostgreSQL
celery                               # job queue production, nếu cần
boto3                                # chỉ cần nếu dùng S3-compatible storage
```

Tên và phiên bản package cần chốt lại theo Python version, CPU/GPU và cách đóng gói Docker.

### Configuration mới

Trong [`src/app/config.py`](../src/app/config.py), thay các biến Azure bằng nhóm biến như:

```text
MODEL_PATH
MODEL_DEVICE=cpu|cuda
OCR_ENGINE=paddleocr|tesseract
OCR_MODEL_PATH
STORAGE_ROOT
DATABASE_URL
BROKER_URL
```

Không nên bắt buộc các biến Azure ở bước validate configuration. Các client nên được khởi tạo lazy để service có thể chạy với từng backend độc lập.

## 9. Docker và tài liệu cần cập nhật

File [`src/.devcontainer/docker-compose.yml`](../src/.devcontainer/docker-compose.yml) hiện có Azure SQL Edge. Khi rebuild cần thay bằng các service local, tối thiểu:

```text
app
postgres
```

Có thể thêm:

```text
worker
redis hoặc rabbitmq
seaweedfs
```

Các tài liệu cần cập nhật:

- [`README.md`](../README.md): mô tả lại kiến trúc self-hosted và bỏ hướng dẫn Azure bắt buộc.
- [`docs/architecture.md`](architecture.md): thay sơ đồ Azure bằng sơ đồ local/open-source.
- [`docs/local_development_setup.md`](local_development_setup.md): hướng dẫn PostgreSQL, model weights và OCR local.
- [`docs/user-guide.md`](user-guide.md): cập nhật các biến môi trường và cách chạy API.
- [`docs/design-db.md`](design-db.md): cập nhật database schema mới.
- `.env.sample` hoặc các file environment tương ứng: bỏ Azure endpoint/credential.
- Dockerfile và dependency lock file nếu có: bổ sung system package cho OCR và GPU khi cần.

## 10. Thành phần cần bổ sung nếu muốn bám sát paper

Việc thay Azure chỉ giúp pipeline chạy local; nó không tự làm source code giống hoàn toàn paper. Nếu mục tiêu là đạt đầy đủ chức năng của paper, cần xem xét bổ sung:

- Phát hiện line signs và flow arrows bằng model riêng.
- Nhận diện tee/cross fitting và nối line bị đứt.
- Loại bỏ chu kỳ graph sai và gộp các đoạn line liên tiếp.
- Phân loại piping line và signal line.
- Suy luận hướng dòng chảy.
- Xây dựng exporter sang mô hình dữ liệu DEXPI hoặc schema tương đương.
- Bổ sung bước human review để sửa symbol/text/topology có confidence thấp.

Các thuật toán line detection và graph construction hiện tại có thể dùng làm nền tảng cho những phần này.

## 11. Lộ trình triển khai đề xuất

### Giai đoạn 1: chạy local tối thiểu

- [ ] Tạo interface `SymbolDetector`, `OcrEngine`, `StorageBackend`.
- [ ] Thay Blob bằng `LocalStorageBackend`.
- [ ] Thay Azure OCR bằng PaddleOCR hoặc CRAFT + Tesseract.
- [ ] Thay Azure ML API bằng local symbol detector.
- [ ] Giữ nguyên line detection và graph construction.
- [ ] Chạy được một P&ID end-to-end không có internet.

### Giai đoạn 2: persistence và xử lý ổn định

- [ ] Chuyển SQL Server Graph sang PostgreSQL hoặc PostgreSQL + AGE.
- [ ] Thay queue trong RAM bằng Celery nếu cần nhiều worker.
- [ ] Lưu job status và kết quả vào database.
- [ ] Cập nhật Docker Compose và test integration.

### Giai đoạn 3: product hóa

- [ ] Thêm model registry và versioning cho detector/OCR.
- [ ] Thêm human review cho kết quả có confidence thấp.
- [ ] Bổ sung topology rules theo paper.
- [ ] Xuất JSON/CSV/DEXPI và API truy vấn graph.
- [ ] Thêm monitoring, backup và phân quyền người dùng.

## 12. Tiêu chí hoàn thành bản rebuild

Bản rebuild được xem là loại bỏ phụ thuộc Azure khi:

1. `src/requirements.txt` không còn Azure SDK, `pyodbc` hoặc package cloud bắt buộc.
2. Service khởi động được chỉ với các service local.
3. Có thể chạy symbol detection và OCR bằng model local.
4. Input/output/debug image không cần Azure Blob.
5. Graph được lưu và truy vấn bằng PostgreSQL/AGE.
6. Có test end-to-end trên bộ P&ID mẫu.
7. Có tài liệu license cho source code, model weights, dataset và các dependency.

## 13. Stack đề xuất

### MVP một máy

```text
FastAPI
MMDetection hoặc detector PyTorch local
PaddleOCR
OpenCV + Shapely + NetworkX
Local filesystem
PostgreSQL
```

### Production self-hosted

```text
FastAPI
Local model worker
PaddleOCR/Tesseract worker
Celery + RabbitMQ/Redis
PostgreSQL hoặc PostgreSQL + AGE
SeaweedFS hoặc object storage nội bộ
Prometheus
```

Không nên chọn một framework chỉ vì framework đó open-source; cần kiểm tra riêng license của framework, model weights, dataset và điều kiện phân phối sản phẩm. Ví dụ, Ultralytics công bố lựa chọn AGPL-3.0 hoặc commercial license, nên phải đánh giá kỹ nếu sản phẩm là proprietary: [Ultralytics licensing](https://www.ultralytics.com/legal).

## 14. So sánh pipeline của source code với paper

Paper tham chiếu: [End-to-end digitization of image format piping and instrumentation diagrams at an industrially applicable level](https://doi.org/10.1093/jcde/qwac056).

### 14.1. Pipeline hiện tại của source code

```text
Ảnh P&ID
  -> tiền xử lý ảnh
  -> symbol detection
       Azure ML YOLOv2 endpoint
       output: bounding box, class, confidence
  -> text detection
       Azure Document Intelligence OCR
       output: text, polygon, text-symbol association
  -> line detection
       xóa vùng symbol/text
       grayscale, threshold, thinning
       Hough transform
       output: line segments, direction/type
  -> graph construction
       NetworkX + Shapely
       mở rộng line
       tìm candidate theo intersection/distance
       nối line-line, line-symbol, symbol-symbol
       xử lý arrow và BFS graph traversal
  -> graph persistence
       SQL Server Graph/Azure SQL
       API và Blob Storage lưu intermediate output
```

Source code được thiết kế theo nhiều API tuần tự. Người dùng có thể sửa kết quả symbol hoặc text trước khi chạy bước tiếp theo. Vì vậy pipeline hiện tại vừa là inference pipeline, vừa là workflow có human-in-the-loop.

Các mô tả chi tiết nằm trong [`architecture.md`](architecture.md), [`text-detection-design.md`](text-detection-design.md), [`line-detection-design.md`](line-detection-design.md) và [`graph-construction-design.md`](graph-construction-design.md).

### 14.2. Pipeline trong paper

```text
Ảnh P&ID
  -> object recognition
       symbol: GFL, hai mạng small/large, 76 loại symbol
       text: CRAFT + Tesseract
       line sign/flow arrow: RetinaNet
       line ngang/dọc: pixel traversal
       line chéo: Hough + AND operation
       thinning và xử lý ảnh
  -> topology reconstruction
       merge/segment line
       loại penetration và line giả
       ghép text-symbol-line
       nối line-line, symbol-line, symbol-symbol
       loại cycle sai
       nối line bị đứt
       nhận diện tee/cross fitting
       gộp line nối tiếp
       phân biệt piping line/signal line
       định hướng line và flow
  -> digital P&ID generation
       mô hình dữ liệu DEXPI
       2D symbol catalogue
       sinh/nhận diện ID bằng regex
       bổ sung engineering attributes
```

Paper mô tả một phương pháp nghiên cứu end-to-end, trong đó kết quả cuối không chỉ là graph hình học mà là digital P&ID có cấu trúc và ngữ nghĩa kỹ thuật.

### 14.3. Điểm giống nhau

| Khía cạnh | Mức độ giống nhau |
|---|---|
| Mục tiêu | Đều chuyển ảnh P&ID thành dữ liệu có cấu trúc để biểu diễn thiết bị, đường ống, text và quan hệ kết nối. |
| Các đối tượng chính | Đều xử lý symbol, text và line trước khi dựng topology. |
| Kết hợp ML và hình học | Đều dùng model nhận diện kết hợp với quy tắc về vị trí, khoảng cách, giao nhau và kết nối. |
| Text-symbol association | Đều gán text gần hoặc nằm trong symbol để xác định thông tin thiết bị. |
| Line connectivity | Đều cần nối line với line, line với symbol và xử lý các trường hợp line bị ngắt hoặc giao nhau. |
| Flow direction | Đều có bước xử lý arrow/direction để suy luận hướng dòng hoặc quan hệ kết nối. |
| Graph representation | Đều biểu diễn các thành phần thành node và quan hệ thành edge. |

Nói cách khác, source code giữ lại cùng một decomposition cấp cao như paper:

```text
recognition -> association -> topology -> structured representation
```

### 14.4. Điểm khác nhau chính

| Công đoạn | Source code | Paper | Đánh giá |
|---|---|---|---|
| Symbol detection | Azure ML endpoint chạy YOLOv2; source docs mô tả bộ dữ liệu synthetic 500 P&ID và 32 symbol, chia thành equipment/piping/instrumentation. | GFL với hai network và 76 loại symbol. | Cùng mục đích nhưng khác model, số lớp và dataset. |
| OCR | Azure Document Intelligence `prebuilt-read`, có high-resolution OCR. | CRAFT phát hiện text và Tesseract nhận dạng ký tự. | Cùng output text + tọa độ nhưng khác hoàn toàn engine. |
| Line detection | Chủ yếu tiền xử lý, loại vùng symbol/text rồi dùng Hough transform để tạo line segment. | Pipeline chuyên biệt cho line signs/flow arrows, line ngang/dọc và line chéo. | Paper chi tiết và chuyên biệt hơn, đặc biệt với arrow và line orientation. |
| Liên kết đối tượng | Quy tắc khoảng cách/intersection và proximity matching. | Ghép đối tượng trong topology reconstruction rồi tiếp tục các bước refinement. | Source có cùng nền tảng nhưng heuristic đơn giản hơn. |
| Xử lý topology | NetworkX/Shapely, extend line, closest element, arrow rematch, symbol proximity và BFS traversal. | Có thêm cycle removal, broken-line connection, tee/cross recognition, serial-line combination và piping/signal classification. | Đây là khác biệt kỹ thuật lớn nhất. |
| Flow direction | Có xử lý arrow và propagation trong graph. | Có bước định hướng line và suy luận flow trong topology hoàn chỉnh. | Source có nền tảng nhưng chưa tương đương đầy đủ paper. |
| Đầu ra | Intermediate JSON, hình debug, graph NetworkX và graph lưu trong SQL Graph. | Digital P&ID theo DEXPI/data model, có catalogue và engineering attributes. | Paper có semantic output đầy đủ hơn; source thiên về graph persistence. |
| Human-in-the-loop | API cho phép sửa symbol/text trước khi chạy bước tiếp theo. | Có bổ sung engineering attributes và kiểm tra dữ liệu trong quy trình số hóa. | Cả hai đều không hoàn toàn tự động, nhưng điểm can thiệp khác nhau. |
| Training/evaluation | Source chính là inference service; training symbol model nằm ngoài repository. | Paper trình bày toàn bộ phương pháp và benchmark trên bộ P&ID thử nghiệm. | Source không phải bản code tái hiện đầy đủ thí nghiệm của paper. |
| Hạ tầng | FastAPI, Azure ML, Azure OCR, Blob Storage, Azure SQL Graph. | Mô tả pipeline/phương pháp nghiên cứu, không bị ràng buộc bởi kiến trúc Azure của source. | Khác ở tầng triển khai, không phải mục tiêu bài toán. |

### 14.5. Kết luận về mức độ tương đồng

Hai pipeline giải quyết cùng bài toán ở cấp độ mục tiêu và các bước chính, nhưng không phải cùng một implementation.

Có thể xem source code là:

```text
paper-inspired pipeline
+ production API workflow
+ Azure model/OCR/storage/database
- một số topology refinement nâng cao của paper
- digital P&ID/DEXPI output đầy đủ
```

Phần tương đồng mạnh nhất là:

```text
symbol/text/line detection
  -> association
  -> graph/topology construction
```

Phần source còn thiếu hoặc đơn giản hơn paper là:

- detector line sign/flow arrow chuyên biệt;
- xử lý tee/cross và broken line nâng cao;
- loại cycle sai và gộp line nối tiếp;
- phân loại piping line với signal line;
- semantic digital P&ID và DEXPI exporter.

### 14.6. Hướng kết hợp phù hợp

Nếu xây dựng sản phẩm mới, nên dùng source code làm skeleton dịch vụ và dùng paper làm reference cho thuật toán:

1. Giữ FastAPI, preprocessing, text-symbol association, line detection hiện tại và graph construction hiện có.
2. Thay Azure detector/OCR/storage/database bằng các adapter local/open-source theo các phần trước.
3. Bổ sung từng topology refinement của paper sau khi pipeline local chạy ổn định.
4. Thiết kế thêm lớp semantic model để xuất digital P&ID/DEXPI thay vì chỉ lưu graph hình học.
5. Dùng golden test P&ID để đo riêng symbol, OCR, line, topology và đầu ra cuối.

Vì vậy, việc rebuild không nên bắt đầu bằng việc viết lại toàn bộ pipeline. Cách ít rủi ro hơn là giữ contract giữa các bước, thay dependency bên ngoài trước, sau đó nâng cấp các bước topology và semantic output theo paper.
