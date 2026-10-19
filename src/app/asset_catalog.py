"""Plant asset profiles and live tag occurrences in saved P&ID data."""

from __future__ import annotations

import hashlib
import math
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from psycopg import errors
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app import document_storage as storage

router = APIRouter(prefix="/api/v1", tags=["assets"])
MAX_FILE_BYTES = 20 * 1024 * 1024
FILE_TYPES = {
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".tif",
    ".tiff",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".csv",
    ".txt",
}
CATEGORIES = r"^(datasheet|manual|photo|inspection|maintenance|other)$"


def normalize(value: str) -> str:
    return " ".join(value.split()).casefold()


def normalize_tag(value: str) -> str:
    return re.sub(r"\s+", "", value.translate(str.maketrans("–—−", "---"))).upper()


def init_tables(db) -> None:
    db.execute("""CREATE TABLE IF NOT EXISTS drawing_review_scenes (
        drawing_id VARCHAR(32) NOT NULL REFERENCES drawing_documents(id) ON DELETE CASCADE,
        page_number INTEGER NOT NULL CHECK (page_number > 0),
        job_id TEXT NOT NULL, data JSONB NOT NULL, saved_at TIMESTAMPTZ NOT NULL,
        PRIMARY KEY (drawing_id, page_number)
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS plant_assets (
        id VARCHAR(32) PRIMARY KEY, project TEXT NOT NULL, area TEXT NOT NULL,
        tag TEXT NOT NULL, name TEXT NOT NULL, equipment_type TEXT NOT NULL, notes TEXT NOT NULL,
        project_key TEXT NOT NULL, area_key TEXT NOT NULL, tag_key TEXT NOT NULL,
        version INTEGER NOT NULL DEFAULT 1, created_at TIMESTAMPTZ NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL, UNIQUE(project_key, area_key, tag_key)
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS plant_asset_occurrences (
        id VARCHAR(32) PRIMARY KEY,
        asset_id VARCHAR(32) NOT NULL REFERENCES plant_assets(id) ON DELETE CASCADE,
        drawing_id VARCHAR(32) NOT NULL REFERENCES drawing_documents(id) ON DELETE CASCADE,
        page_number INTEGER NOT NULL, source TEXT NOT NULL, kind TEXT NOT NULL,
        item_id TEXT NOT NULL, generation TEXT NOT NULL, source_tag TEXT NOT NULL,
        UNIQUE(drawing_id, page_number, source, kind, item_id, generation)
    )""")
    db.execute("""CREATE INDEX IF NOT EXISTS asset_occurrences_asset_idx
        ON plant_asset_occurrences(asset_id)""")
    db.execute("""ALTER TABLE plant_asset_occurrences
        ADD COLUMN IF NOT EXISTS source_symbol_code TEXT NOT NULL DEFAULT ''""")
    db.execute("""CREATE TABLE IF NOT EXISTS plant_asset_documents (
        id VARCHAR(32) PRIMARY KEY,
        asset_id VARCHAR(32) NOT NULL REFERENCES plant_assets(id) ON DELETE CASCADE,
        title TEXT NOT NULL, category TEXT NOT NULL, url TEXT NOT NULL DEFAULT '',
        filename TEXT NOT NULL DEFAULT '', bucket TEXT NOT NULL DEFAULT '',
        object_key TEXT NOT NULL DEFAULT '', byte_size BIGINT NOT NULL DEFAULT 0,
        sha256 TEXT NOT NULL DEFAULT '', created_at TIMESTAMPTZ NOT NULL
    )""")
    db.execute("""CREATE INDEX IF NOT EXISTS asset_documents_asset_idx
        ON plant_asset_documents(asset_id)""")


def save_review_scene(drawing_id: str, job_id: str, data: dict, page_number: int = 1) -> None:
    # Page identity comes from the server job, never the editable client scene.
    with storage.connection() as db:
        if not db.execute(
            "SELECT id FROM drawing_documents WHERE id = %s FOR UPDATE", (drawing_id,)
        ).fetchone():
            raise HTTPException(404, "Không tìm thấy bản vẽ.")
        db.execute(
            """INSERT INTO drawing_review_scenes (drawing_id, page_number, job_id, data, saved_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (drawing_id, page_number) DO UPDATE SET
            job_id = EXCLUDED.job_id, data = EXCLUDED.data, saved_at = EXCLUDED.saved_at,
            version = drawing_review_scenes.version + 1""",
            (drawing_id, page_number, job_id, Jsonb(data), data["review"]["saved_at"]),
        )


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class AssetFields(StrictModel):
    project: str = Field(min_length=1, max_length=120)
    area: str = Field(default="", max_length=120)
    tag: str = Field(min_length=1, max_length=120)
    name: str = Field(default="", max_length=240)
    equipment_type: str = Field(default="", max_length=120)
    notes: str = Field(default="", max_length=10000)


class AssetUpdate(AssetFields):
    version: int = Field(ge=1)


class OccurrenceRef(StrictModel):
    drawing_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    page_number: int = Field(ge=1)
    source: str = Field(pattern=r"^(annotation|review)$")
    kind: str = Field(pattern=r"^(symbol|text)$")
    item_id: str = Field(min_length=1, max_length=120)
    generation: str = Field(default="", max_length=120)
    tag: str = Field(default="", max_length=120)
    symbol_code: str = Field(default="", max_length=120)


class AssetCreate(AssetFields):
    occurrence: OccurrenceRef | None = None


class DocumentLink(StrictModel):
    title: str = Field(min_length=1, max_length=240)
    category: str = Field(default="other", pattern=CATEGORIES)
    url: str = Field(min_length=1, max_length=2048)

    @field_validator("url")
    @classmethod
    def safe_url(cls, value):
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or any(ord(char) < 32 for char in value)
        ):
            raise ValueError("Đường dẫn phải là HTTP/HTTPS, không chứa thông tin đăng nhập.")
        return value


def asset_or_404(db, asset_id, lock=False):
    row = db.execute(
        "SELECT * FROM plant_assets WHERE id = %s" + (" FOR UPDATE" if lock else ""),
        (asset_id,),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Không tìm thấy hồ sơ thiết bị.")
    return row


def asset_payload(row):
    return {key: value for key, value in row.items() if not key.endswith("_key")}


def box(item):
    try:
        values = {key: float(item[key]) for key in ("x", "y", "width", "height")}
        if all(math.isfinite(value) for value in values.values()) and (
            values["x"] >= 0 and values["y"] >= 0 and values["width"] > 0 and values["height"] > 0
        ):
            return values
    except (KeyError, TypeError, ValueError):
        pass
    return None


def extract_occurrences(row):
    """Use explicit text_of links only; do not guess asset identity by proximity."""
    data, metadata = row["data"], row["metadata"]
    symbols = {
        str(item["id"]): item
        for item in data.get("symbols", [])
        if isinstance(item, dict) and "id" in item
    }
    texts = {
        str(item["id"]): item
        for item in data.get("texts", [])
        if isinstance(item, dict) and "id" in item
    }
    linked = {}
    used_texts = set()
    for relation in data.get("relations", []):
        if isinstance(relation, dict) and relation.get("type") == "text_of":
            source, target = str(relation.get("source")), str(relation.get("target"))
            if source in texts and target in symbols:
                linked.setdefault(target, []).append(texts[source])
                used_texts.add(source)
    candidates = []
    for id_, symbol in symbols.items():
        tags = (
            [symbol["tag"]]
            if symbol.get("tag")
            else [item.get("text", "") for item in linked.get(id_, [])]
        )
        # A library code identifies the symbol class, not an equipment tag.
        # Keep untagged symbols discoverable without inventing asset identity.
        if not tags and symbol.get("label_id"):
            tags = [""]
        for tag in dict.fromkeys(str(value).strip() for value in tags):
            candidates.append(("symbol", id_, symbol, tag))
    for id_, text in texts.items():
        if id_ not in used_texts:
            candidates.append(("text", id_, text, str(text.get("text", "")).strip()))
    classes = {
        item["code"]: item
        for item in data.get("classes", [])
        if isinstance(item, dict) and "code" in item
    }
    workflow = metadata.get("page_workflows", {}).get(str(row["page_number"]), {})
    for kind, id_, item, tag in candidates:
        bounds = box(item)
        symbol_code = item.get("label_id", "") if kind == "symbol" else ""
        if (not tag and not symbol_code) or len(tag) > 120 or bounds is None:
            continue
        yield {
            "drawing_id": row["drawing_id"],
            "page_number": row["page_number"],
            "source": row["source"],
            "kind": kind,
            "item_id": id_,
            "generation": row.get("job_id", ""),
            "tag": tag,
            "symbol_code": symbol_code,
            "drawing_name": metadata["original_name"],
            "project": metadata.get("project", ""),
            "drawing_set": metadata.get("drawing_set", ""),
            "drawing_number": metadata.get("drawing_number", ""),
            "revision_label": metadata.get("revision_label", ""),
            "lifecycle": metadata.get("lifecycle", "current"),
            "equipment_type": item.get("type")
            or classes.get(item.get("label_id"), {}).get("name", item.get("label_id", "")),
            "review_status": "saved_review"
            if row["source"] == "review"
            else workflow.get("status", "in_progress"),
            "confidence": item.get("confidence"),
            "box": bounds,
        }


def source_rows(db, drawing_id=None):
    # Read no drawing bytes. Source annotations remain the authority, so edits
    # and deletions become searchable immediately without a second stale index.
    return db.execute(
        """SELECT a.drawing_id, a.page_number, a.data, d.metadata,
            'annotation' AS source, '' AS job_id FROM drawing_annotations a
            JOIN drawing_documents d ON d.id = a.drawing_id
            WHERE (%s::text IS NULL OR a.drawing_id = %s)
        UNION ALL
        SELECT r.drawing_id, r.page_number, r.data, d.metadata,
            'review' AS source, r.job_id FROM drawing_review_scenes r
            JOIN drawing_documents d ON d.id = r.drawing_id
            WHERE (%s::text IS NULL OR r.drawing_id = %s)""",
        (drawing_id, drawing_id, drawing_id, drawing_id),
    ).fetchall()


def occurrence_key(item):
    return tuple(
        item[key]
        for key in ("drawing_id", "page_number", "source", "kind", "item_id", "generation")
    )


def live_occurrences(db, drawing_id=None):
    links = {
        occurrence_key(row): row
        for row in db.execute("SELECT * FROM plant_asset_occurrences").fetchall()
    }
    assets = {
        row["id"]: row
        for row in db.execute("SELECT id, project_key, project, tag FROM plant_assets").fetchall()
    }
    for row in source_rows(db, drawing_id):
        for item in extract_occurrences(row):
            link = links.get(occurrence_key(item))
            asset = assets.get(link["asset_id"]) if link else None
            valid = (
                asset
                and (
                    not normalize(item["project"])
                    or asset["project_key"] == normalize(item["project"])
                )
                and link["source_tag"] == normalize_tag(item["tag"])
                and (bool(item["tag"]) or link["source_symbol_code"] == item["symbol_code"])
            )
            yield {
                **item,
                "asset_id": asset["id"] if valid else None,
                "link_id": link["id"] if valid else None,
                "asset_tag": asset["tag"] if valid else "",
                "asset_project": asset["project"] if valid else "",
            }


@router.get("/asset-search")
def search_tags(
    q: str = Query(default="", max_length=120),
    project: str = Query(default="", max_length=120),
    include_superseded: bool = False,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
):
    with storage.connection() as db:
        matches = [
            item
            for item in live_occurrences(db)
            if (
                not q.strip()
                or any(
                    normalize_tag(q) in normalize_tag(item[key])
                    for key in ("tag", "symbol_code", "asset_tag")
                )
            )
            and (
                not project
                or normalize(project)
                in (normalize(item["project"]), normalize(item["asset_project"]))
            )
            and (include_superseded or item["lifecycle"] != "superseded")
        ]
    matches.sort(
        key=lambda item: (
            normalize_tag(q)
            not in (
                normalize_tag(item["tag"]),
                normalize_tag(item["symbol_code"]),
                normalize_tag(item["asset_tag"]),
            ),
            normalize_tag(item["tag"] or item["asset_tag"] or item["symbol_code"]),
            item["drawing_name"],
            item["page_number"],
            item["source"],
            item["item_id"],
        )
    )
    return {"items": matches[offset : offset + limit], "total": len(matches)}


@router.get("/assets")
def list_assets(
    q: str = Query(default="", max_length=120),
    project: str = Query(default="", max_length=120),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
):
    with storage.connection() as db:
        rows = db.execute(
            "SELECT * FROM plant_assets ORDER BY tag_key, project_key, area_key"
        ).fetchall()
    matches = [
        asset_payload(row)
        for row in rows
        if (not project or normalize(project) == row["project_key"])
        and (
            not q.strip()
            or normalize(q)
            in normalize(" ".join(row[key] for key in ("tag", "name", "equipment_type", "area")))
            or normalize_tag(q) in row["tag_key"]
        )
    ]
    return {"items": matches[offset : offset + limit], "total": len(matches)}


def link_occurrence(db, asset, ref):
    if not ref.tag and (ref.kind != "symbol" or not ref.symbol_code):
        raise HTTPException(422, "Chọn một symbol có mã loại hoặc một vị trí có tag để liên kết.")
    if not db.execute(
        "SELECT id FROM drawing_documents WHERE id = %s FOR UPDATE", (ref.drawing_id,)
    ).fetchone():
        raise HTTPException(404, "Không tìm thấy bản vẽ.")
    current = next(
        (
            item
            for item in live_occurrences(db, ref.drawing_id)
            if occurrence_key(item) == occurrence_key(ref.model_dump())
            and normalize_tag(item["tag"]) == normalize_tag(ref.tag)
            and (ref.tag or item["symbol_code"] == ref.symbol_code)
        ),
        None,
    )
    if not current:
        raise HTTPException(409, "Vị trí hoặc tag đã thay đổi. Làm mới kết quả tìm kiếm.")
    if normalize(current["project"]) and normalize(current["project"]) != asset["project_key"]:
        raise HTTPException(
            422, "Thiết bị và bản vẽ phải thuộc cùng dự án. Gán dự án cho bản vẽ trong Data trước."
        )
    if current["asset_id"] and current["asset_id"] != asset["id"]:
        raise HTTPException(409, "Vị trí này đã được gắn vào thiết bị khác. Gỡ liên kết cũ trước.")
    db.execute(
        """INSERT INTO plant_asset_occurrences
        (id, asset_id, drawing_id, page_number, source, kind, item_id, generation, source_tag,
        source_symbol_code)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (drawing_id, page_number, source, kind, item_id, generation)
        DO UPDATE SET asset_id = EXCLUDED.asset_id, source_tag = EXCLUDED.source_tag,
        source_symbol_code = EXCLUDED.source_symbol_code""",
        (
            uuid.uuid4().hex,
            asset["id"],
            *occurrence_key(ref.model_dump()),
            normalize_tag(ref.tag),
            current["symbol_code"],
        ),
    )


@router.post("/assets", status_code=201)
def create_asset(request: AssetCreate):
    now = datetime.now(timezone.utc)
    values = request.model_dump(exclude={"occurrence"})
    row = dict(
        id=uuid.uuid4().hex,
        **values,
        project_key=normalize(request.project),
        area_key=normalize(request.area),
        tag_key=normalize_tag(request.tag),
        version=1,
        created_at=now,
        updated_at=now,
    )
    try:
        with storage.connection() as db:
            db.execute(
                """INSERT INTO plant_assets (id, project, area, tag, name, equipment_type, notes,
                project_key, area_key, tag_key, version, created_at, updated_at)
                VALUES (%(id)s, %(project)s, %(area)s, %(tag)s, %(name)s, %(equipment_type)s,
                %(notes)s, %(project_key)s, %(area_key)s, %(tag_key)s, %(version)s,
                %(created_at)s, %(updated_at)s)""",
                row,
            )
            if request.occurrence:
                link_occurrence(db, row, request.occurrence)
    except errors.UniqueViolation as error:
        raise HTTPException(
            409, "Tag đã có hồ sơ trong dự án/khu vực này. Chọn hồ sơ hiện có để liên kết."
        ) from error
    return asset_payload(row)


@router.get("/assets/{asset_id}")
def get_asset(asset_id: str):
    with storage.connection() as db:
        row = asset_or_404(db, asset_id)
        occurrences = [item for item in live_occurrences(db) if item["asset_id"] == asset_id]
        links = db.execute(
            "SELECT * FROM plant_asset_occurrences WHERE asset_id = %s", (asset_id,)
        ).fetchall()
        live_ids = {item["link_id"] for item in occurrences}
        documents = db.execute(
            """SELECT id, title, category, url, filename, byte_size,
            sha256, created_at FROM plant_asset_documents WHERE asset_id = %s
            ORDER BY created_at DESC, id""",
            (asset_id,),
        ).fetchall()
    return {
        **asset_payload(row),
        "occurrences": occurrences,
        "stale_links": [
            {"id": item["id"], "drawing_id": item["drawing_id"], "page_number": item["page_number"]}
            for item in links
            if item["id"] not in live_ids
        ],
        "documents": [
            {
                **item,
                "download_url": f"/api/v1/assets/{asset_id}/documents/{item['id']}/download"
                if item["filename"]
                else None,
            }
            for item in documents
        ],
    }


@router.put("/assets/{asset_id}")
def update_asset(asset_id: str, request: AssetUpdate):
    try:
        with storage.connection() as db:
            current = asset_or_404(db, asset_id, lock=True)
            if current["version"] != request.version:
                raise HTTPException(409, "Hồ sơ đã thay đổi ở phiên khác. Tải lại trước khi lưu.")
            if (
                normalize(request.project) != current["project_key"]
                and db.execute(
                    "SELECT 1 FROM plant_asset_occurrences WHERE asset_id = %s LIMIT 1", (asset_id,)
                ).fetchone()
            ):
                raise HTTPException(409, "Gỡ các liên kết bản vẽ trước khi chuyển dự án.")
            values = dict(
                request.model_dump(),
                id=asset_id,
                project_key=normalize(request.project),
                area_key=normalize(request.area),
                tag_key=normalize_tag(request.tag),
            )
            row = db.execute(
                """UPDATE plant_assets SET project = %(project)s, area = %(area)s,
                tag = %(tag)s, name = %(name)s, equipment_type = %(equipment_type)s,
                notes = %(notes)s, project_key = %(project_key)s, area_key = %(area_key)s,
                tag_key = %(tag_key)s, version = version + 1, updated_at = CURRENT_TIMESTAMP
                WHERE id = %(id)s RETURNING *""",
                values,
            ).fetchone()
    except errors.UniqueViolation as error:
        raise HTTPException(409, "Tag đã có hồ sơ trong dự án/khu vực này.") from error
    return asset_payload(row)


@router.post("/assets/{asset_id}/occurrences", status_code=201)
def attach_occurrence(asset_id: str, request: OccurrenceRef):
    with storage.connection() as db:
        asset = asset_or_404(db, asset_id, lock=True)
        link_occurrence(db, asset, request)
    return {"linked": True}


@router.delete("/assets/{asset_id}/occurrences/{link_id}")
def detach_occurrence(asset_id: str, link_id: str):
    with storage.connection() as db:
        asset_or_404(db, asset_id)
        if not db.execute(
            "DELETE FROM plant_asset_occurrences WHERE id = %s AND asset_id = %s RETURNING id",
            (link_id, asset_id),
        ).fetchone():
            raise HTTPException(404, "Không tìm thấy liên kết.")
    return {"deleted": True}


@router.post("/assets/{asset_id}/documents/links", status_code=201)
def add_document_link(asset_id: str, request: DocumentLink):
    with storage.connection() as db:
        asset_or_404(db, asset_id)
        row = db.execute(
            """INSERT INTO plant_asset_documents
            (id, asset_id, title, category, url, created_at) VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            RETURNING id""",
            (uuid.uuid4().hex, asset_id, request.title, request.category, request.url),
        ).fetchone()
    return row


@router.post("/assets/{asset_id}/documents/upload", status_code=201)
def upload_asset_document(
    asset_id: str,
    file: UploadFile = File(...),
    title: str = Form(default="", max_length=240),
    category: str = Form(default="other", pattern=CATEGORIES),
):
    filename = (file.filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    if not filename or len(filename) > 240 or any(ord(char) < 32 for char in filename):
        raise HTTPException(422, "Tên tệp không hợp lệ.")
    if Path(filename).suffix.lower() not in FILE_TYPES:
        raise HTTPException(415, "Hỗ trợ PDF, ảnh, Word, Excel, CSV và TXT.")
    digest = hashlib.sha256()
    size = 0
    while chunk := file.file.read(1024 * 1024):
        size += len(chunk)
        if size > MAX_FILE_BYTES:
            raise HTTPException(413, "Tài liệu tối đa 20 MB.")
        digest.update(chunk)
    if not size:
        raise HTTPException(422, "Tệp không được rỗng.")
    file.file.seek(0)
    id_ = uuid.uuid4().hex
    key = f"assets/{asset_id}/{id_}{Path(filename).suffix.lower()}"
    bucket = os.getenv("MINIO_BUCKET", "pid-drawings")
    with storage.connection() as db:
        asset_or_404(db, asset_id, lock=True)
        client = storage.client()
        client.put_object(bucket, key, file.file, size, content_type="application/octet-stream")
        try:
            db.execute(
                """INSERT INTO plant_asset_documents
                (id, asset_id, title, category, filename, bucket, object_key, byte_size, sha256, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)""",
                (
                    id_,
                    asset_id,
                    title.strip() or filename,
                    category,
                    filename,
                    bucket,
                    key,
                    size,
                    digest.hexdigest(),
                ),
            )
            # Commit while cleanup is still possible if the transaction fails.
            db.commit()
        except Exception:
            client.remove_object(bucket, key)
            raise
    return {"id": id_}


@router.get("/assets/{asset_id}/documents/{document_id}/download")
def download_asset_document(asset_id: str, document_id: str):
    with storage.connection() as db:
        row = db.execute(
            "SELECT * FROM plant_asset_documents WHERE id = %s AND asset_id = %s",
            (document_id, asset_id),
        ).fetchone()
    if not row or not row["object_key"]:
        raise HTTPException(404, "Không tìm thấy tệp đính kèm.")
    response = storage.client().get_object(row["bucket"], row["object_key"])

    def chunks():
        try:
            yield from response.stream(1024 * 1024)
        finally:
            response.close()
            response.release_conn()

    return StreamingResponse(
        chunks(),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(row['filename'], safe='')}",
            "Content-Length": str(row["byte_size"]),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.delete("/assets/{asset_id}/documents/{document_id}")
def delete_asset_document(asset_id: str, document_id: str):
    with storage.connection() as db:
        row = db.execute(
            "SELECT * FROM plant_asset_documents WHERE id = %s AND asset_id = %s FOR UPDATE",
            (document_id, asset_id),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Không tìm thấy tài liệu.")
        if row["object_key"]:
            storage.client().remove_object(row["bucket"], row["object_key"])
        db.execute("DELETE FROM plant_asset_documents WHERE id = %s", (document_id,))
    return {"deleted": True}
