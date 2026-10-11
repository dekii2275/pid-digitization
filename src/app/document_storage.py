"""MinIO owns drawing bytes; PostgreSQL owns metadata and manual annotations."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import uuid
from pathlib import Path

from fastapi import HTTPException
from minio import Minio
from minio.error import S3Error
from psycopg.types.json import Jsonb
from urllib3 import PoolManager, Retry, Timeout

from app.symbol_library import connection


def client() -> Minio:
    return Minio(
        os.getenv("MINIO_ENDPOINT", "localhost:18735"),
        access_key=os.getenv("MINIO_ACCESS_KEY", "pid_minio"),
        secret_key=os.getenv("MINIO_SECRET_KEY", "change-this-minio-password"),
        secure=os.getenv("MINIO_SECURE", "false").lower() == "true",
        http_client=PoolManager(timeout=Timeout(connect=5, read=60), retries=Retry(total=2)),
    )


DOCUMENT_QUERY = """SELECT d.*, COALESCE(a.annotation_count, 0) AS annotation_count,
    COALESCE(a.labeled_pages, '[]'::jsonb) AS labeled_pages, a.last_labeled_at
    FROM drawing_documents d
    LEFT JOIN LATERAL (
        SELECT SUM(jsonb_array_length(data->'symbols') + jsonb_array_length(data->'texts'))
            AS annotation_count,
            jsonb_agg(page_number ORDER BY page_number) FILTER (
                WHERE jsonb_array_length(data->'symbols') + jsonb_array_length(data->'texts') > 0
            ) AS labeled_pages,
            MAX(saved_at) AS last_labeled_at
        FROM drawing_annotations WHERE drawing_id = d.id
    ) a ON TRUE"""


def unpack(row: dict) -> dict:
    return {
        **row["metadata"],
        "drawing_id": row["id"],
        "bucket": row["bucket"],
        "object_key": row["object_key"],
        "byte_size": row["byte_size"],
        "sha256": row["sha256"],
        "annotation_count": int(row["annotation_count"]),
        "labeled_pages": row["labeled_pages"],
        "last_labeled_at": row["last_labeled_at"].isoformat() if row["last_labeled_at"] else None,
    }


def get_document(drawing_id: str) -> dict | None:
    with connection() as db:
        row = db.execute(DOCUMENT_QUERY + " WHERE d.id = %s", (drawing_id,)).fetchone()
    return unpack(row) if row else None


def list_documents(labeled: bool | None = None) -> list[dict]:
    query = DOCUMENT_QUERY
    if labeled is not None:
        query += " WHERE (COALESCE(a.annotation_count, 0) > 0) = %s"
    with connection() as db:
        rows = db.execute(
            query + " ORDER BY d.created_at DESC, d.id", (labeled,) if labeled is not None else ()
        ).fetchall()
    return [unpack(row) for row in rows]


def save_source(drawing_id: str, source: Path, metadata: dict) -> dict:
    bucket = os.getenv("MINIO_BUCKET", "pid-drawings")
    key = f"drawings/{drawing_id}/original{metadata['extension']}"
    digest = hashlib.sha256()
    with source.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    content_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
    storage = client()
    storage.fput_object(bucket, key, str(source), content_type=content_type)
    try:
        with connection() as db:
            db.execute(
                """INSERT INTO drawing_documents (id, bucket, object_key, byte_size, sha256, metadata, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (
                    drawing_id,
                    bucket,
                    key,
                    source.stat().st_size,
                    digest.hexdigest(),
                    Jsonb(metadata),
                    metadata["created_at"],
                ),
            )
    except Exception:
        # A failed database transaction must not leave an unlisted uploaded object.
        storage.remove_object(bucket, key)
        raise
    return {
        **metadata,
        "drawing_id": drawing_id,
        "bucket": bucket,
        "object_key": key,
        "byte_size": source.stat().st_size,
        "sha256": digest.hexdigest(),
        "annotation_count": 0,
        "labeled_pages": [],
        "last_labeled_at": None,
    }


def cache_source(document: dict, destination: Path) -> Path:
    if destination.is_file():
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f"{destination.name}.{uuid.uuid4().hex}.tmp")
    try:
        client().fget_object(document["bucket"], document["object_key"], str(temporary))
        if hashlib.sha256(temporary.read_bytes()).hexdigest() != document["sha256"]:
            raise HTTPException(503, "File bản vẽ trong kho lưu trữ không khớp checksum.")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def delete_document(drawing_id: str) -> dict:
    with connection() as db:
        row = db.execute(
            "SELECT * FROM drawing_documents WHERE id = %s FOR UPDATE", (drawing_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Không tìm thấy bản vẽ.")
        # Keep the catalog entry if MinIO cannot confirm removal. Retrying a
        # successful object deletion is safe even if the subsequent commit fails.
        client().remove_object(row["bucket"], row["object_key"])
        db.execute("DELETE FROM drawing_documents WHERE id = %s", (drawing_id,))
    return row["metadata"]


def read_annotation(drawing_id: str, page: int) -> dict | None:
    with connection() as db:
        row = db.execute(
            "SELECT data FROM drawing_annotations WHERE drawing_id = %s AND page_number = %s",
            (drawing_id, page),
        ).fetchone()
    return row["data"] if row else None


def save_annotation(drawing_id: str, page: int, data: dict, expected_revision: int) -> None:
    with connection() as db:
        if not db.execute(
            "SELECT id FROM drawing_documents WHERE id = %s FOR UPDATE", (drawing_id,)
        ).fetchone():
            raise HTTPException(404, "Không tìm thấy bản vẽ.")
        existing = db.execute(
            "SELECT data FROM drawing_annotations WHERE drawing_id = %s AND page_number = %s",
            (drawing_id, page),
        ).fetchone()
        if (existing["data"]["revision"] if existing else 0) != expected_revision:
            raise HTTPException(
                409, "Nhãn đã thay đổi ở phiên khác. Tải lại bản lưu trước khi tiếp tục."
            )
        db.execute(
            """INSERT INTO drawing_annotations (drawing_id, page_number, data, saved_at)
            VALUES (%s, %s, %s, %s) ON CONFLICT (drawing_id, page_number)
            DO UPDATE SET data = EXCLUDED.data, saved_at = EXCLUDED.saved_at""",
            (drawing_id, page, Jsonb(data), data["saved_at"]),
        )


def sync_classes(catalog: list[dict]) -> list[dict]:
    with connection() as db:
        row = db.execute(
            "SELECT data FROM drawing_annotation_classes WHERE id = 1 FOR UPDATE"
        ).fetchone()
        classes = row["data"]
        known = {item["code"] for item in classes}
        for item in sorted(catalog, key=lambda item: item["code"]):
            if item["enabled"] and item["code"] not in known:
                classes.append(
                    {
                        "id": len(classes),
                        "code": item["code"],
                        "name": item["name"],
                        "category": item["category"],
                    }
                )
                known.add(item["code"])
        db.execute(
            "UPDATE drawing_annotation_classes SET data = %s WHERE id = 1", (Jsonb(classes),)
        )
    return classes


def init_documents(legacy_root: Path) -> None:
    storage = client()
    bucket = os.getenv("MINIO_BUCKET", "pid-drawings")
    if not storage.bucket_exists(bucket):
        try:
            storage.make_bucket(bucket)
        except S3Error as error:
            if error.code not in {"BucketAlreadyOwnedByYou", "BucketAlreadyExists"}:
                raise
    with connection() as db:
        db.execute("SELECT pg_advisory_xact_lock(20309179)")
        db.execute("""CREATE TABLE IF NOT EXISTS drawing_documents (
            id VARCHAR(32) PRIMARY KEY,
            bucket TEXT NOT NULL,
            object_key TEXT NOT NULL UNIQUE,
            byte_size BIGINT NOT NULL,
            sha256 VARCHAR(64) NOT NULL,
            metadata JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS drawing_annotations (
            drawing_id VARCHAR(32) NOT NULL REFERENCES drawing_documents(id) ON DELETE CASCADE,
            page_number INTEGER NOT NULL CHECK (page_number > 0),
            data JSONB NOT NULL,
            saved_at TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (drawing_id, page_number)
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS drawing_annotation_classes (
            id INTEGER PRIMARY KEY CHECK (id = 1), data JSONB NOT NULL
        )""")
        class_path = legacy_root / "annotations/classes.json"
        legacy_classes = (
            json.loads(class_path.read_text(encoding="utf-8")) if class_path.is_file() else []
        )
        db.execute(
            "INSERT INTO drawing_annotation_classes VALUES (1, %s) ON CONFLICT DO NOTHING",
            (Jsonb(legacy_classes),),
        )
        db.execute("CREATE TABLE IF NOT EXISTS drawing_storage_migrations (name TEXT PRIMARY KEY)")
        if db.execute(
            "SELECT 1 FROM drawing_storage_migrations WHERE name = 'local-files-v1'"
        ).fetchone():
            return
        # Preserve the old sources as backups. This one-time marker prevents a
        # deleted drawing from being re-imported on the next service restart.
        for path in sorted(legacy_root.glob("*.json")):
            if not re.fullmatch(r"[a-f0-9]{32}", path.stem):
                continue
            metadata = json.loads(path.read_text(encoding="utf-8"))
            if metadata["extension"] not in {".pdf", ".png", ".jpg", ".jpeg"}:
                raise ValueError(f"Unsupported legacy document: {path.name}")
            source = legacy_root / f"{path.stem}{metadata['extension']}"
            if not source.is_file():
                raise FileNotFoundError(f"Missing legacy drawing: {path.name}")
            key = f"drawings/{path.stem}/original{metadata['extension']}"
            storage.fput_object(
                bucket,
                key,
                str(source),
                content_type=mimetypes.guess_type(source.name)[0] or "application/octet-stream",
            )
            db.execute(
                """INSERT INTO drawing_documents VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING""",
                (
                    path.stem,
                    bucket,
                    key,
                    source.stat().st_size,
                    hashlib.sha256(source.read_bytes()).hexdigest(),
                    Jsonb(metadata),
                    metadata["created_at"],
                ),
            )
            for annotation in (legacy_root / "annotations" / path.stem).glob("page-*.json"):
                data = json.loads(annotation.read_text(encoding="utf-8"))
                db.execute(
                    "INSERT INTO drawing_annotations VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
                    (path.stem, data["source"]["page_number"], Jsonb(data), data["saved_at"]),
                )
        db.execute("INSERT INTO drawing_storage_migrations VALUES ('local-files-v1')")
