# Chạy dự án bằng Docker

## Dịch vụ và cổng

| Dịch vụ | Cổng trong container | Cổng mặc định trên máy chủ |
| --- | ---: | ---: |
| Giao diện React (qua Nginx) | 8080 | `18731` |
| FastAPI / Swagger | 8000 | `18732` |
| PostgreSQL | 5432 | `127.0.0.1:18733` |
| Redis | 6379 | `127.0.0.1:18734` |

Mặc định Compose chạy frontend và backend. PostgreSQL, Redis và worker chỉ khởi động với profile `full-stack`. PostgreSQL và Redis chỉ nghe ở loopback. Tất cả cổng đều đổi được trong `.env`.

## Khởi động

1. Cài Docker Engine hoặc Docker Desktop.
2. Từ thư mục gốc repository, tạo file cấu hình:

   ```sh
   cp .env.docker.example .env
   ```

   Trên Windows PowerShell dùng: `Copy-Item .env.docker.example .env`.
   Thay `POSTGRES_PASSWORD` bằng mật khẩu mạnh trước khi triển khai.
3. Đặt model (ví dụ `best.pt`) vào `models/` nếu pipeline của bạn cần. Thư mục `uploads/`, `artifacts/` và `models/` được bind-mount để dữ liệu/model còn nguyên sau khi tái tạo container.
4. Build và chạy:

   ```sh
   docker compose up --build -d
   ```

Lệnh trên khởi động UI và API xem/xử lý bản vẽ. Để khởi động thêm worker, PostgreSQL và Redis, dùng `docker compose --profile full-stack up --build -d`. Profile này không tự chạy `alembic upgrade head`; hãy chạy migration riêng nếu dùng chức năng lưu vào database.

> PostgreSQL chỉ đọc `POSTGRES_PASSWORD` khi khởi tạo volume lần đầu. Nếu bạn đã từng chạy stack với mật khẩu khác và chưa có dữ liệu cần giữ, chạy `docker compose down -v` rồi khởi động lại. Lệnh đó xoá hoàn toàn database và Redis, nên hãy sao lưu trước khi dùng trên môi trường có dữ liệu.

- Ứng dụng: `http://<server>:18731`
- Swagger: `http://<server>:18732/docs`
- Theo dõi log: `docker compose logs -f`
- Dừng: `docker compose down` (không xoá database)

## Sao lưu database

```sh
docker compose exec -T db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > pid_db.sql
```

Trên PowerShell, thay hai biến bằng giá trị trong `.env` nếu terminal không nạp file đó. Không dùng `docker compose down -v` trừ khi bạn muốn xoá hoàn toàn PostgreSQL và Redis.
