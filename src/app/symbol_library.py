"""PostgreSQL-backed catalog of reviewed P&ID symbol definitions and files."""

from __future__ import annotations

import hashlib
import io
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import psycopg
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from PIL import Image, ImageOps, UnidentifiedImageError
from psycopg import errors
from psycopg.rows import dict_row

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = Path(
    os.getenv(
        "SYMBOL_LIBRARY_DIR",
        str(Path(os.getenv("DRAWING_STORAGE_DIR", str(REPO_ROOT / "uploads"))) / "symbol-library"),
    )
)
DB_PATH = ROOT / "symbols.sqlite3"  # Read-only legacy source; kept after migration.
ASSET_DIR = ROOT / "assets"  # Legacy files; new imports live in PostgreSQL.
SEED_DIR = Path(__file__).with_name("seed_symbols")
MAX_SOURCE = 20 * 1024 * 1024
MAX_PREVIEW = 5 * 1024 * 1024
SOURCE_EXTENSIONS = {
    ".dwg",
    ".dxf",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
    ".pdf",
}
SOURCE_IMAGE_EXTENSIONS = SOURCE_EXTENSIONS - {".dwg", ".dxf", ".pdf"}
PREVIEW_EXTENSIONS = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}
router = APIRouter(prefix="/api/v1/symbol-library", tags=["symbol-library"])


def connection() -> psycopg.Connection:
    """Open one transaction; Compose passes discrete settings to avoid URL escaping."""
    url = os.getenv("SYMBOL_DATABASE_URL")
    if url:
        return psycopg.connect(url, row_factory=dict_row, connect_timeout=10)
    return psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        user=os.getenv("POSTGRES_USER", "pid_app"),
        password=os.getenv("POSTGRES_PASSWORD", "change-this-password"),
        dbname=os.getenv("POSTGRES_DB", "pid_db"),
        row_factory=dict_row,
        connect_timeout=10,
    )


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _migrate_sqlite(db: psycopg.Connection) -> None:
    """Copy the old catalog once, including original bytes; never delete it."""
    if not DB_PATH.is_file():
        return
    with closing(sqlite3.connect(DB_PATH)) as old:
        old.row_factory = sqlite3.Row
        if not old.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='symbol_definitions'"
        ).fetchone():
            return
        for row in old.execute("SELECT * FROM symbol_definitions ORDER BY code"):
            db.execute(
                """INSERT INTO symbol_definitions
                   (code, name, category, enabled, origin, preview_left, preview_top,
                    preview_width, preview_height, created_at, updated_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (code) DO NOTHING""",
                (
                    row["code"],
                    row["name"],
                    row["category"],
                    bool(row["enabled"]),
                    row["origin"],
                    row["preview_left"],
                    row["preview_top"],
                    row["preview_width"],
                    row["preview_height"],
                    _timestamp(row["created_at"]),
                    _timestamp(row["updated_at"]),
                ),
            )
        for row in old.execute("SELECT * FROM symbol_assets ORDER BY id"):
            path = ASSET_DIR / row["storage_name"]
            if not path.is_file():
                raise RuntimeError(f"Legacy symbol asset is missing: {path}")
            data = path.read_bytes()
            if len(data) != row["byte_size"] or hashlib.sha256(data).hexdigest() != row["sha256"]:
                raise RuntimeError(f"Legacy symbol asset checksum mismatch: {path}")
            db.execute(
                """INSERT INTO symbol_assets
                   (symbol_code, role, filename, content_type, sha256, byte_size, data, created_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (symbol_code, role) DO NOTHING""",
                (
                    row["symbol_code"],
                    row["role"],
                    row["filename"],
                    row["content_type"],
                    row["sha256"],
                    row["byte_size"],
                    data,
                    _timestamp(row["created_at"]),
                ),
            )


def init_library() -> None:
    """Create the catalog, migrate SQLite once, then seed only an empty catalog."""
    with connection() as db:
        # Serializes migration/seed if multiple API workers start together.
        db.execute("SELECT pg_advisory_xact_lock(20309178)")
        db.execute("""CREATE TABLE IF NOT EXISTS symbol_definitions (
            code VARCHAR(64) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            category VARCHAR(100) NOT NULL,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            origin VARCHAR(100) NOT NULL,
            preview_left INTEGER,
            preview_top INTEGER,
            preview_width INTEGER,
            preview_height INTEGER,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS symbol_assets (
            id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            symbol_code VARCHAR(64) NOT NULL REFERENCES symbol_definitions(code) ON DELETE CASCADE,
            role VARCHAR(7) NOT NULL CHECK (role IN ('source', 'preview')),
            filename TEXT NOT NULL,
            content_type TEXT NOT NULL,
            sha256 CHAR(64) NOT NULL,
            byte_size BIGINT NOT NULL,
            data BYTEA NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            UNIQUE (symbol_code, role)
        )""")
        db.execute(
            "CREATE INDEX IF NOT EXISTS ix_symbol_definitions_category ON symbol_definitions(category)"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS symbol_library_state (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )

        if not db.execute(
            "SELECT 1 FROM symbol_library_state WHERE key = 'sqlite_imported'"
        ).fetchone():
            _migrate_sqlite(db)
            db.execute(
                "INSERT INTO symbol_library_state (key, value) VALUES ('sqlite_imported', '1')"
            )

        if not db.execute("SELECT 1 FROM symbol_library_state WHERE key = 'seeded'").fetchone():
            if not db.execute("SELECT 1 FROM symbol_definitions LIMIT 1").fetchone():
                now = datetime.now(timezone.utc)
                for code, name, source, left in (
                    ("CRV-001", "Check Return Valve", "Check Return Valve.dwg", 78),
                    ("GLV-001", "Global Valve", "Global valve.dwg", 174),
                ):
                    db.execute(
                        """INSERT INTO symbol_definitions
                           (code, name, category, origin, preview_left, preview_top,
                            preview_width, preview_height, created_at, updated_at)
                           VALUES (%s, %s, 'Valves', 'PPID_SYMBOL', %s, 40, 47, 210, %s, %s)""",
                        (code, name, left, now, now),
                    )
                    for role, filename, path, mime in (
                        ("source", source, SEED_DIR / source, "application/acad"),
                        ("preview", "PNG.png", SEED_DIR / "PNG.png", "image/png"),
                    ):
                        data = path.read_bytes()
                        db.execute(
                            """INSERT INTO symbol_assets
                               (symbol_code, role, filename, content_type, sha256, byte_size, data, created_at)
                               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                            (
                                code,
                                role,
                                filename,
                                mime,
                                hashlib.sha256(data).hexdigest(),
                                len(data),
                                data,
                                now,
                            ),
                        )
            db.execute("INSERT INTO symbol_library_state (key, value) VALUES ('seeded', '1')")


def payload(row: dict) -> dict:
    item = dict(row)
    for field in ("created_at", "updated_at"):
        if isinstance(item.get(field), datetime):
            item[field] = item[field].isoformat()
    item["preview"] = f"/api/v1/symbol-library/{item['code']}/preview"
    item["source_url"] = f"/api/v1/symbol-library/{item['code']}/source"
    item["id"] = item["code"]
    return item


@router.get("")
def list_symbols() -> list[dict]:
    with connection() as db:
        rows = db.execute(
            "SELECT * FROM symbol_definitions ORDER BY category, name, code"
        ).fetchall()
    return [payload(row) for row in rows]


async def read_upload(file: UploadFile, *, extensions: set[str], limit: int) -> tuple[str, bytes]:
    filename = (file.filename or "").replace("\\", "/").split("/")[-1]
    extension = Path(filename).suffix.lower()
    if extension not in extensions:
        raise HTTPException(
            415, f"Định dạng tệp không được hỗ trợ: {extension or 'không có phần mở rộng'}."
        )
    data = await file.read(limit + 1)
    if not data or len(data) > limit:
        raise HTTPException(413, f"Tệp phải có dữ liệu và không quá {limit // 1024 // 1024} MB.")
    return filename, data


def preview_from_source(filename: str, data: bytes) -> tuple[str, bytes]:
    """Keep the original upload and derive a browser-friendly catalog image."""
    extension = Path(filename).suffix.lower()
    if extension not in SOURCE_IMAGE_EXTENSIONS:
        raise HTTPException(
            422,
            "Hãy chọn ảnh PNG, JPG, WEBP, BMP hoặc TIFF. File DWG, DXF và PDF cần ảnh xem trước riêng khi nhập qua API.",
        )
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            if image.width < 8 or image.height < 8 or image.width * image.height > 25_000_000:
                raise ValueError("Kích thước ảnh symbol không hợp lệ.")
            if Image.registered_extensions().get(extension) != image.format:
                raise ValueError("Định dạng ảnh không khớp phần mở rộng.")
            with ImageOps.exif_transpose(image) as normalized:
                normalized.thumbnail((512, 512))
                output = io.BytesIO()
                normalized.convert("RGBA").save(output, format="PNG")
        return f"{Path(filename).stem}.png", output.getvalue()
    except (
        UnidentifiedImageError,
        Image.DecompressionBombError,
        OSError,
        ValueError,
        SyntaxError,
    ) as error:
        raise HTTPException(422, f"Ảnh gốc symbol không hợp lệ: {error}") from error


@router.post("/import", status_code=201)
async def import_symbol(
    code: str = Form(...),
    name: str = Form(...),
    category: str = Form("Other"),
    source: UploadFile = File(...),
    preview: UploadFile | None = File(None),
) -> dict:
    code, name, category = code.strip().upper(), name.strip(), category.strip()
    if (
        not code
        or len(code) > 64
        or not all(char.isascii() and (char.isalnum() or char in "-_") for char in code)
    ):
        raise HTTPException(
            422, "Mã symbol chỉ được gồm chữ ASCII, số, dấu - hoặc _ (tối đa 64 ký tự)."
        )
    if not name or len(name) > 255 or not category or len(category) > 100:
        raise HTTPException(422, "Tên và nhóm symbol phải có nội dung, không vượt giới hạn độ dài.")
    source_name, source_data = await read_upload(
        source, extensions=SOURCE_EXTENSIONS, limit=MAX_SOURCE
    )
    if preview is None:
        preview_name, preview_data = preview_from_source(source_name, source_data)
    else:
        preview_name, preview_data = await read_upload(
            preview, extensions=set(PREVIEW_EXTENSIONS), limit=MAX_PREVIEW
        )
    try:
        with Image.open(io.BytesIO(preview_data)) as image:
            image.verify()
        with Image.open(io.BytesIO(preview_data)) as image:
            if image.width < 8 or image.height < 8 or image.width * image.height > 25_000_000:
                raise ValueError("Kích thước ảnh xem trước không hợp lệ.")
            if (image.format or "").lower() != Path(preview_name).suffix.lower().lstrip(
                "."
            ).replace("jpg", "jpeg"):
                raise ValueError("Định dạng ảnh không khớp phần mở rộng.")
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError) as error:
        raise HTTPException(422, f"Ảnh xem trước không hợp lệ: {error}") from error
    now = datetime.now(timezone.utc)
    try:
        with connection() as db:
            db.execute(
                """INSERT INTO symbol_definitions
                   (code, name, category, origin, created_at, updated_at)
                   VALUES (%s, %s, %s, 'web-import', %s, %s)""",
                (code, name, category, now, now),
            )
            for role, filename, data, mime in (
                (
                    "source",
                    source_name,
                    source_data,
                    source.content_type or "application/octet-stream",
                ),
                (
                    "preview",
                    preview_name,
                    preview_data,
                    PREVIEW_EXTENSIONS[Path(preview_name).suffix.lower()],
                ),
            ):
                db.execute(
                    """INSERT INTO symbol_assets
                       (symbol_code, role, filename, content_type, sha256, byte_size, data, created_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                    (
                        code,
                        role,
                        filename,
                        mime,
                        hashlib.sha256(data).hexdigest(),
                        len(data),
                        data,
                        now,
                    ),
                )
            row = db.execute("SELECT * FROM symbol_definitions WHERE code = %s", (code,)).fetchone()
        return payload(row)
    except errors.UniqueViolation as error:
        raise HTTPException(409, f"Mã {code} đã tồn tại. Hãy dùng mã khác.") from error


@router.patch("/{code}")
def update_symbol(code: str, changes: dict) -> dict:
    allowed = {"name", "category", "enabled"}
    if not changes or set(changes) - allowed:
        raise HTTPException(422, "Chỉ có thể sửa tên, nhóm và trạng thái.")
    if "name" in changes and (
        not isinstance(changes["name"], str)
        or not changes["name"].strip()
        or len(changes["name"]) > 255
    ):
        raise HTTPException(422, "Tên symbol không hợp lệ.")
    if "category" in changes and (
        not isinstance(changes["category"], str)
        or not changes["category"].strip()
        or len(changes["category"]) > 100
    ):
        raise HTTPException(422, "Nhóm symbol không hợp lệ.")
    if "enabled" in changes and not isinstance(changes["enabled"], bool):
        raise HTTPException(422, "Trạng thái phải là true hoặc false.")
    values = {
        key: value.strip() if isinstance(value, str) else value for key, value in changes.items()
    }
    values["updated_at"] = datetime.now(timezone.utc)
    with connection() as db:
        assignments = ", ".join(f"{key} = %s" for key in values)
        row = db.execute(
            f"UPDATE symbol_definitions SET {assignments} WHERE code = %s RETURNING *",
            (*values.values(), code),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Không tìm thấy symbol.")
    return payload(row)


@router.delete("/{code}", status_code=204)
def delete_symbol(code: str) -> Response:
    with connection() as db:
        row = db.execute(
            "DELETE FROM symbol_definitions WHERE code = %s RETURNING code", (code,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Không tìm thấy symbol.")
    return Response(status_code=204)


@router.get("/{code}/{role}")
def get_symbol_asset(code: str, role: str) -> Response:
    if role not in {"source", "preview"}:
        raise HTTPException(404, "Không tìm thấy tệp.")
    with connection() as db:
        asset = db.execute(
            "SELECT filename, content_type, data FROM symbol_assets WHERE symbol_code = %s AND role = %s",
            (code, role),
        ).fetchone()
    if not asset:
        raise HTTPException(404, "Không tìm thấy tệp.")
    headers = {}
    if role == "source":
        headers["Content-Disposition"] = (
            f"attachment; filename*=UTF-8''{quote(asset['filename'], safe='')}"
        )
    return Response(content=asset["data"], media_type=asset["content_type"], headers=headers)
