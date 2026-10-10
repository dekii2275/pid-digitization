# Chạy dự án bằng Docker

## Yêu cầu

- Git và Docker Desktop (Linux containers) hoặc Docker Engine với Compose v2
  hỗ trợ `up --wait`.
- Máy x86-64, tối thiểu 8 GB RAM cho pipeline CPU và khoảng 10 GB đĩa trống.
- Internet khi build lần đầu và khi PaddleOCR tải model lần đầu.
- Checkpoint YOLO đã được kèm ở `models/symbol-detector/best.pt`.

## Khởi động từ bản clone mới

```sh
git clone https://github.com/dekii2275/pid-digitization.git
cd pid-digitization
cp .env.docker.example .env
docker compose up --build -d --wait --wait-timeout 180
```

Trên PowerShell dùng `Copy-Item .env.docker.example .env` thay cho `cp`.
Chỉ tạo `.env` nếu chưa có; không ghi đè cấu hình đang dùng. Thay mật khẩu
trong file trước khi triển khai lên server. Build đầu tiên tải các dependency
AI nên có thể mất nhiều phút. Pipeline chạy CPU, không cần GPU/CUDA.

Nếu clone workspace `vpi_detectandocr`, dùng `start.ps1` hoặc `sh start.sh`
ở thư mục workspace để tự khởi tạo submodule và chạy các bước trên.

| Dịch vụ | Cổng trên máy chủ |
| --- | --- |
| React / Nginx | `18731` |
| FastAPI / Swagger | `18732` |
| PostgreSQL | `127.0.0.1:18733` |

Mặc định chạy **frontend, backend và PostgreSQL**. Mở
`http://localhost:18731`, tải ảnh/PDF, rồi chạy pipeline. Với PDF, pipeline
hiện xử lý trang đầu. Thư viện symbol được seed tự động khi database mới
khởi tạo. Không cần chạy Alembic cho API web mặc định (`app.web_main`).

Các cổng thay đổi được trong `.env`. Frontend dùng `/api/v1` qua Nginx,
nên hoạt động cả khi truy cập bằng IP/domain server. Kiểm tra sức khỏe trực
tiếp ở `http://localhost:18732/health`.

## Dữ liệu và vận hành

- Symbol và file nguồn/preview nằm trong Docker volume `postgres_data`.
- File upload, preview, tile và kết quả pipeline nằm trong `uploads/`,
  `artifacts/`; detector được mount chỉ đọc từ `models/`.
- Metadata bản vẽ và job hiện nằm trong RAM. Sau restart backend cần upload
  lại bản vẽ; file vật lý và thư viện symbol vẫn được giữ.
- Theo dõi log: `docker compose logs -f backend`.
- Dừng và giữ dữ liệu: `docker compose down`.
- Cập nhật: `git pull`, rồi `docker compose up --build -d --wait`.
- Không dùng `docker compose down -v` khi cần giữ database: tùy chọn `-v`
  xóa volume và dữ liệu PostgreSQL.

PostgreSQL nhận mật khẩu khi volume khởi tạo lần đầu. Khi đổi mật khẩu của
database đã có dữ liệu, cập nhật tài khoản trong PostgreSQL và cấu hình `.env`
cùng nhau; thay mỗi `.env` sẽ làm backend không kết nối được.

Sao lưu (biến được đọc trong container, không phụ thuộc shell máy chủ):

```sh
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > pid_db.sql
```

Sao lưu cả `uploads/` và `artifacts/` nếu cần giữ bản vẽ và kết quả.

## Kiểm thử

CI build container thật, chạy kiểm thử API và PostgreSQL trên database tạm,
khởi động đủ ba dịch vụ và kiểm tra API qua Nginx. Chạy tương tự ở máy local:

```sh
docker compose exec -T backend pip install -r src/requirements.test.txt
docker compose exec -T -e SYMBOL_TEST_DATABASE=1 backend python -m unittest discover -s tests -p 'test_symbol_library.py' -v
docker compose exec -T backend python -m unittest discover -s tests -p 'test_web_main.py' -v
python scripts/smoke_web.py --base-url http://localhost:18731
```

## Các workflow khác

`src/app/main.py`, worker Redis và Alembic thuộc API cũ. Profile `full-stack`
giữ worker/Redis cho phát triển API đó; worker không nhận job từ API review
mặc định. Xem `src/README.md` và `docs/project-layout.md` trước khi dùng.
Dataset huấn luyện không cần cho ứng dụng web. Windows GPU/OCR bootstrap là
môi trường thí nghiệm riêng; Docker CPU là cách chạy chuẩn được kiểm thử.
