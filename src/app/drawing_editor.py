"""Durable page editing, optimistic saves and CAD handoff independent of jobs."""

from __future__ import annotations

import copy
import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field

from app import document_storage as storage

COLLECTIONS = ("symbols", "texts", "lines", "topology_edges")
MAX_ITEMS = 20000


def init_tables(db):
    db.execute("""ALTER TABLE drawing_review_scenes
        ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1""")
    db.execute("""CREATE TABLE IF NOT EXISTS drawing_processed_scenes (
        drawing_id VARCHAR(32) NOT NULL REFERENCES drawing_documents(id) ON DELETE CASCADE,
        page_number INTEGER NOT NULL CHECK (page_number > 0), job_id TEXT NOT NULL,
        data JSONB NOT NULL, saved_at TIMESTAMPTZ NOT NULL,
        PRIMARY KEY (drawing_id, page_number)
    )""")


def save_processed_scene(drawing_id, page, job_id, scene):
    with storage.connection() as db:
        if not db.execute(
            "SELECT id FROM drawing_documents WHERE id = %s FOR UPDATE", (drawing_id,)
        ).fetchone():
            raise HTTPException(404, "Không tìm thấy bản vẽ.")
        db.execute(
            """INSERT INTO drawing_processed_scenes
            (drawing_id, page_number, job_id, data, saved_at) VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (drawing_id, page_number) DO UPDATE SET job_id = EXCLUDED.job_id,
            data = EXCLUDED.data, saved_at = EXCLUDED.saved_at""",
            (drawing_id, page, job_id, Jsonb(scene)),
        )


def import_legacy_results(root: Path):
    """Recover older completed jobs without replacing any existing database edit."""
    paths = sorted(
        root.glob("*/job_*/editor/scene.json"), key=lambda path: path.stat().st_mtime, reverse=True
    )
    for path in paths:
        drawing_id, job_id = path.parents[2].name, path.parents[1].name
        try:
            context_path = path.parents[1] / "page-context.json"
            page = (
                int(json.loads(context_path.read_text())["page_number"])
                if context_path.is_file()
                else 1
            )
            with storage.connection() as db:
                document = db.execute(
                    "SELECT metadata FROM drawing_documents WHERE id = %s FOR UPDATE", (drawing_id,)
                ).fetchone()
                if not document or not 1 <= page <= document["metadata"]["page_count"]:
                    continue
                for name, table in (
                    ("scene.json", "drawing_processed_scenes"),
                    ("final-scene.json", "drawing_review_scenes"),
                ):
                    source = path.with_name(name)
                    if (
                        not source.is_file()
                        or db.execute(
                            f"SELECT 1 FROM {table} WHERE drawing_id = %s AND page_number = %s",
                            (drawing_id, page),
                        ).fetchone()
                    ):
                        continue
                    data = json.loads(source.read_text(encoding="utf-8"))
                    if not isinstance(data, dict) or not all(
                        isinstance(data.get(key), list) for key in COLLECTIONS
                    ):
                        continue
                    db.execute(
                        f"""INSERT INTO {table} (drawing_id, page_number, job_id, data, saved_at)
                        VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""",
                        (
                            drawing_id,
                            page,
                            job_id,
                            Jsonb(data),
                            datetime.fromtimestamp(source.stat().st_mtime, timezone.utc),
                        ),
                    )
        except (ValueError, OSError, KeyError, TypeError):
            logging.getLogger(__name__).warning("Bỏ qua kết quả cũ không hợp lệ: %s", path.name)


def cad_kind(symbol):
    explicit = symbol.get("cad_kind")
    if explicit in {
        "pump",
        "valve",
        "check_valve",
        "globe_valve",
        "connector",
        "instrument",
        "vessel",
        "other",
    }:
        return explicit
    name = f"{symbol.get('type', '')} {symbol.get('category', '')}".lower()
    code = str(symbol.get("label_id") or "").upper()
    if code == "LC-001" or any(
        term in name
        for term in ("off-page", "off page", "line connection", "signal line within a unit")
    ):
        return "connector"
    if code == "VALVES-012" or (
        "valve" in name and any(term in name for term in ("check", "non return", "non-return"))
    ):
        return "check_valve"
    if code == "VALVES-020" or "globe valve" in name:
        return "globe_valve"
    for kind, terms in (
        ("valve", ("valve",)),
        ("pump", ("pump", "compressor", "blower")),
        ("instrument", ("instrument", "indicator", "transmitter", "gauge")),
        ("vessel", ("vessel", "tank", "drum", "column", "separator", "exchanger")),
    ):
        if any(term in name for term in terms):
            return kind
    return "other"


def line_points(item):
    if isinstance(item.get("points"), list):
        points = item["points"]
    elif isinstance(item.get("start"), list) and isinstance(item.get("end"), list):
        points = [item["start"], item["end"]]
    else:
        points = [[item.get("x1"), item.get("y1")], [item.get("x2"), item.get("y2")]]
    if not 2 <= len(points) <= 10000:
        raise ValueError("Đường ống phải có từ 2 đến 10000 điểm.")
    result = []
    for point in points:
        if isinstance(point, dict):
            point = [point.get("x"), point.get("y")]
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise ValueError("Tọa độ đường ống không hợp lệ.")
        values = [float(value) for value in point]
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Tọa độ phải là số hữu hạn.")
        result.append(values)
    return result


def normalize_scene(scene, drawing_id, page, width, height, name):
    try:
        data = json.loads(json.dumps(scene, ensure_ascii=False, allow_nan=False))
        ids = {}
        for collection in COLLECTIONS:
            items = data.setdefault(collection, [])
            if not isinstance(items, list) or len(items) > MAX_ITEMS:
                raise ValueError("Số đối tượng vượt giới hạn hoặc dữ liệu không hợp lệ.")
            seen = set()
            for item in items:
                if not isinstance(item, dict):
                    raise ValueError("Mỗi đối tượng phải có cấu trúc hợp lệ.")
                id_ = str(item.get("id", ""))
                if not id_ or len(id_) > 120 or id_ in seen:
                    raise ValueError("ID đối tượng bị thiếu hoặc trùng trong cùng nhóm.")
                item["id"] = id_
                seen.add(id_)
            ids[collection] = seen
        if ids["symbols"] & ids["texts"]:
            raise ValueError("ID symbol và text phải khác nhau.")
        for item in [*data["symbols"], *data["texts"]]:
            for key in ("x", "y", "width", "height"):
                item[key] = float(item[key])
            if (
                not all(math.isfinite(item[key]) for key in ("x", "y", "width", "height"))
                or item["x"] < 0
                or item["y"] < 0
                or item["width"] < 0.5
                or item["height"] < 0.5
                or item["x"] + item["width"] > width + 1e-6
                or item["y"] + item["height"] > height + 1e-6
            ):
                raise ValueError("Đối tượng phải nằm trong kích thước trang.")
            item["rotation"] = float(item.get("rotation", 0)) % 360
            if not math.isfinite(item["rotation"]):
                raise ValueError("Góc xoay phải là số hữu hạn.")
        for symbol in data["symbols"]:
            if not isinstance(symbol.get("tag", ""), str) or len(symbol.get("tag", "")) > 120:
                raise ValueError("Tag tối đa 120 ký tự.")
            if not isinstance(symbol.get("type", ""), str) or len(symbol.get("type", "")) > 240:
                raise ValueError("Loại thiết bị tối đa 240 ký tự.")
            symbol["cad_kind"] = cad_kind(symbol)
        for text in data["texts"]:
            if not isinstance(text.get("text", ""), str) or len(text.get("text", "")) > 4096:
                raise ValueError("Nội dung text tối đa 4096 ký tự.")
        for line in data["lines"]:
            points = line_points(line)
            if any(x < 0 or y < 0 or x > width or y > height for x, y in points):
                raise ValueError("Đường ống phải nằm trong trang.")
            line.update(
                points=points, x1=points[0][0], y1=points[0][1], x2=points[-1][0], y2=points[-1][1]
            )
            line.pop("start", None)
            line.pop("end", None)
        for edge in data["topology_edges"]:
            if (
                str(edge.get("source")) not in ids["symbols"]
                or str(edge.get("target")) not in ids["symbols"]
            ):
                raise ValueError(
                    "Kết nối đang tham chiếu symbol không tồn tại. Sửa hoặc xóa kết nối trước khi lưu."
                )
            edge["source"], edge["target"] = str(edge["source"]), str(edge["target"])
        settings = data.get("cad_settings", {})
        if settings.get("units", "unitless") not in {"unitless", "mm", "inch"}:
            raise ValueError("Đơn vị CAD không hợp lệ.")
        scale = float(settings.get("units_per_pixel", 1))
        if not math.isfinite(scale) or not 0.000001 <= scale <= 1000000:
            raise ValueError("Tỷ lệ CAD phải từ 0.000001 đến 1000000 đơn vị/pixel.")
        data["cad_settings"] = {
            "units": settings.get("units", "unitless"),
            "units_per_pixel": scale,
        }
        data["source"] = {
            "drawing_id": drawing_id,
            "page_number": page,
            "width": width,
            "height": height,
            "name": name,
        }
        return data
    except (ValueError, TypeError, KeyError, OverflowError, AttributeError) as error:
        raise HTTPException(422, f"Không thể lưu bản vẽ: {error}") from error


def annotation_scene(data):
    result = copy.deepcopy(data)
    classes = {item["code"]: item for item in data.get("classes", [])}
    texts = {item["id"]: item for item in data.get("texts", [])}
    for item in result["symbols"]:
        definition = classes.get(item.get("label_id"), {})
        item["type"] = definition.get("name", item.get("label_id", "Symbol"))
        item["category"] = definition.get("category", "")
        item["tag"] = next(
            (
                texts[rel["source"]]["text"]
                for rel in data.get("relations", [])
                if rel.get("type") == "text_of"
                and rel.get("target") == item["id"]
                and rel.get("source") in texts
            ),
            "",
        )
    result["lines"] = []
    result["topology_edges"] = [
        item
        for item in result.get("relations", [])
        if item.get("type") in {"connected_to", "flow_to"}
    ]
    return result


def row_for_page(db, table, drawing_id, page):
    # table is always a literal from this module, never client input.
    return db.execute(
        f"SELECT * FROM {table} WHERE drawing_id = %s AND page_number = %s", (drawing_id, page)
    ).fetchone()


def load_page_scene(drawing_id, page, origin="latest"):
    with storage.connection() as db:
        reviewed = row_for_page(db, "drawing_review_scenes", drawing_id, page)
        processed = row_for_page(db, "drawing_processed_scenes", drawing_id, page)
        annotation = storage.read_annotation(drawing_id, page)
    available = [
        name
        for name, exists in (
            ("review", reviewed),
            ("processed", processed),
            ("annotations", annotation),
        )
        if exists
    ]
    selected = next(iter(available), "empty") if origin == "latest" else origin
    row = {"review": reviewed, "processed": processed}.get(selected)
    if selected == "annotations" and annotation:
        scene, generation = annotation_scene(annotation), f"annotation:{annotation['revision']}"
    elif row:
        scene, generation = row["data"], row["job_id"]
    elif selected == "empty":
        scene, generation = {key: [] for key in COLLECTIONS}, f"manual:{drawing_id}:{page}"
    else:
        raise HTTPException(404, "Trang chưa có kết quả nguồn này.")
    return {
        "scene": scene,
        "generation": generation,
        "version": reviewed["version"] if reviewed else 0,
        "origin": selected,
        "available_sources": available,
        "saved_at": reviewed["saved_at"].isoformat() if selected == "review" else None,
    }


class SceneSaveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    version: int = Field(ge=0)
    generation: str = Field(min_length=1, max_length=160)
    scene: dict


def save_page_scene(drawing_id, page, request, scene):
    with storage.connection() as db:
        document = db.execute(
            "SELECT id FROM drawing_documents WHERE id = %s FOR UPDATE", (drawing_id,)
        ).fetchone()
        if not document:
            raise HTTPException(404, "Không tìm thấy bản vẽ.")
        reviewed = row_for_page(db, "drawing_review_scenes", drawing_id, page)
        version = reviewed["version"] if reviewed else 0
        if version != request.version:
            raise HTTPException(
                409, "Bản vẽ đã được lưu ở phiên khác. Tải lại bản đã lưu trước khi tiếp tục."
            )
        processed = row_for_page(db, "drawing_processed_scenes", drawing_id, page)
        annotation = row_for_page(db, "drawing_annotations", drawing_id, page)
        valid = {row["job_id"] for row in (reviewed, processed) if row}
        if annotation:
            valid.add(f"annotation:{annotation['data']['revision']}")
        if not reviewed and not processed and not annotation:
            valid.add(f"manual:{drawing_id}:{page}")
        if request.generation not in valid:
            raise HTTPException(409, "Kết quả nguồn đã thay đổi. Tải lại trước khi lưu.")
        now = datetime.now(timezone.utc)
        scene["review"] = {"status": "SAVED", "saved_at": now.isoformat(), "version": version + 1}
        db.execute(
            """INSERT INTO drawing_review_scenes (drawing_id, page_number, job_id, data, saved_at, version)
            VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (drawing_id, page_number)
            DO UPDATE SET job_id = EXCLUDED.job_id, data = EXCLUDED.data,
            saved_at = EXCLUDED.saved_at, version = EXCLUDED.version""",
            (drawing_id, page, request.generation, Jsonb(scene), now, version + 1),
        )
    return {
        "saved_at": now.isoformat(),
        "result": scene,
        "version": version + 1,
        "generation": request.generation,
    }


def create_router(page_context):
    router = APIRouter(prefix="/api/v1/documents", tags=["drawing-editor"])

    @router.get("/{drawing_id}/pages/{page_number}/review-scene")
    def get_scene(
        drawing_id: str,
        page_number: int,
        origin: Literal["latest", "review", "processed", "annotations"] = "latest",
    ):
        context = page_context(drawing_id, page_number)
        result = load_page_scene(drawing_id, page_number, origin)
        # Preserve older data, adding only authoritative page metadata and CAD defaults.
        result["scene"]["source"] = context
        result["scene"].setdefault("cad_settings", {"units": "unitless", "units_per_pixel": 1})
        for collection in COLLECTIONS:
            result["scene"].setdefault(collection, [])
        for symbol in result["scene"]["symbols"]:
            symbol.setdefault("cad_kind", cad_kind(symbol))
        for line in result["scene"]["lines"]:
            try:
                points = line_points(line)
            except (TypeError, ValueError) as error:
                raise HTTPException(422, "Tọa độ đường ống nguồn không hợp lệ.") from error
            line.update(
                points=points, x1=points[0][0], y1=points[0][1], x2=points[-1][0], y2=points[-1][1]
            )
            line.pop("start", None)
            line.pop("end", None)
        return result

    @router.put("/{drawing_id}/pages/{page_number}/review-scene")
    def put_scene(drawing_id: str, page_number: int, request: SceneSaveRequest):
        context = page_context(drawing_id, page_number)
        scene = normalize_scene(
            request.scene,
            drawing_id,
            page_number,
            context["width"],
            context["height"],
            context["name"],
        )
        return save_page_scene(drawing_id, page_number, request, scene)

    @router.get("/{drawing_id}/pages/{page_number}/review-scene/export.dxf")
    def export_dxf(drawing_id: str, page_number: int, version: int = Query(ge=1)):
        from app.cad_export import scene_to_dxf

        context = page_context(drawing_id, page_number)
        saved = load_page_scene(drawing_id, page_number, "review")
        if saved["version"] != version:
            raise HTTPException(409, "Bản đã lưu đã thay đổi. Tải lại trước khi xuất DXF.")
        scene = normalize_scene(
            saved["scene"],
            drawing_id,
            page_number,
            context["width"],
            context["height"],
            context["name"],
        )
        filename = f"{Path(context['name']).stem}-p{page_number}-v{version}.dxf"
        return Response(
            scene_to_dxf(scene, saved["generation"]),
            media_type="application/dxf",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename, safe='')}",
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "private, no-store",
            },
        )

    return router
