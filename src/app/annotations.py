"""Manual training annotations, independent of pipeline/review results."""

from __future__ import annotations

import io
import json
import threading
import zipfile
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field

from app.symbol_library import list_symbols


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Box(StrictModel):
    id: str = Field(min_length=1, max_length=100)
    x: float = Field(ge=0)
    y: float = Field(ge=0)
    width: float = Field(ge=1)
    height: float = Field(ge=1)


class SymbolBox(Box):
    label_id: str = Field(min_length=1, max_length=64)


class TextBox(Box):
    text: str = Field(max_length=4096)


class Relation(StrictModel):
    id: str = Field(min_length=1, max_length=100)
    source: str = Field(min_length=1, max_length=100)
    target: str = Field(min_length=1, max_length=100)
    type: str = Field(pattern=r"^(connected_to|flow_to|text_of)$")


class AnnotationRequest(StrictModel):
    revision: int = Field(ge=0)
    symbols: list[SymbolBox] = Field(default_factory=list, max_length=10000)
    texts: list[TextBox] = Field(default_factory=list, max_length=10000)
    relations: list[Relation] = Field(default_factory=list, max_length=20000)


def create_router(record_lookup, page_image, repository):
    router = APIRouter(prefix="/api/v1/documents")
    lock = threading.RLock()

    def context(drawing_id, page_number):
        record = record_lookup(drawing_id)
        image_path = page_image(record, page_number)
        with Image.open(image_path) as image:
            width, height = image.size
        return record, image_path, width, height

    def read(drawing_id, page_number):
        record, _, width, height = context(drawing_id, page_number)
        data = repository.read_annotation(drawing_id, page_number)
        if data is None:
            data = {
                "schema_version": 1,
                "revision": 0,
                "saved_at": None,
                "source": {
                    "drawing_id": drawing_id,
                    "name": record.original_name,
                    "page_number": page_number,
                    "width": width,
                    "height": height,
                },
                "classes": [],
                "symbols": [],
                "texts": [],
                "relations": [],
            }
        # PostgreSQL keeps one stable class mapping across every drawing/page.
        data["classes"] = repository.sync_classes(list_symbols())
        return data

    @router.get("/{drawing_id}/pages/{page_number}/annotations")
    def get_annotations(drawing_id: str, page_number: int):
        with lock:
            return read(drawing_id, page_number)

    @router.put("/{drawing_id}/pages/{page_number}/annotations")
    def save_annotations(drawing_id: str, page_number: int, request: AnnotationRequest):
        with lock:
            data = read(drawing_id, page_number)
            if request.revision != data["revision"]:
                raise HTTPException(
                    409, "Dữ liệu đã được lưu ở phiên khác. Tải lại bản lưu trước khi tiếp tục."
                )
            _, _, width, height = context(drawing_id, page_number)
            ids = [item.id for item in [*request.symbols, *request.texts, *request.relations]]
            if len(ids) != len(set(ids)):
                raise HTTPException(422, "ID của các nhãn và quan hệ phải khác nhau.")
            classes = {item["code"]: item["id"] for item in data["classes"]}
            for item in [*request.symbols, *request.texts]:
                if item.x + item.width > width + 1e-6 or item.y + item.height > height + 1e-6:
                    raise HTTPException(422, "Vùng gán nhãn phải nằm trong kích thước ảnh gốc.")
            for item in request.symbols:
                if item.label_id not in classes:
                    raise HTTPException(422, f"Không tìm thấy nhãn symbol: {item.label_id}.")
            symbols = {item.id for item in request.symbols}
            texts = {item.id for item in request.texts}
            for item in request.relations:
                if item.source == item.target:
                    raise HTTPException(422, "Hai đầu quan hệ phải khác nhau.")
                if item.type == "text_of":
                    valid = item.source in texts and item.target in symbols
                else:
                    valid = item.source in symbols and item.target in symbols
                if not valid:
                    raise HTTPException(
                        422, "Quan hệ nối symbol với symbol; text_of nối OCR với symbol."
                    )
            data.update(
                revision=data["revision"] + 1,
                saved_at=datetime.now(timezone.utc).isoformat(),
                symbols=[
                    dict(item.model_dump(), class_id=classes[item.label_id])
                    for item in request.symbols
                ],
                texts=[item.model_dump() for item in request.texts],
                relations=[item.model_dump() for item in request.relations],
            )
            repository.save_annotation(drawing_id, page_number, data, request.revision)
            return data

    @router.get("/{drawing_id}/pages/{page_number}/annotations/export")
    def export_annotations(drawing_id: str, page_number: int):
        with lock:
            data = read(drawing_id, page_number)
        if data["saved_at"] is None:
            raise HTTPException(409, "Lưu nhãn trước khi xuất dữ liệu.")
        _, image_path, width, height = context(drawing_id, page_number)
        stem = f"{drawing_id}-p{page_number}"
        image_bytes = io.BytesIO()
        with Image.open(image_path) as image:
            image.convert("RGB").save(image_bytes, "PNG")
        yolo = "".join(
            f"{item['class_id']} {(item['x'] + item['width'] / 2) / width:.10f} "
            f"{(item['y'] + item['height'] / 2) / height:.10f} "
            f"{item['width'] / width:.10f} {item['height'] / height:.10f}\n"
            for item in data["symbols"]
        )
        archive_bytes = io.BytesIO()
        with zipfile.ZipFile(archive_bytes, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(f"images/{stem}.png", image_bytes.getvalue())
            archive.writestr(f"labels/{stem}.txt", yolo)
            archive.writestr(
                f"annotations/{stem}.json", json.dumps(data, ensure_ascii=False, indent=2)
            )
            archive.writestr(
                "classes.json", json.dumps(data["classes"], ensure_ascii=False, indent=2)
            )
            archive.writestr(
                "classes.txt", "".join(item["code"] + "\n" for item in data["classes"])
            )
            archive.writestr(
                "data.yaml",
                "path: .\ntrain: images\nnames:\n"
                + "".join(
                    f"  {item['id']}: {json.dumps(item['code'], ensure_ascii=False)}\n"
                    for item in data["classes"]
                ),
            )
            archive.writestr(
                "README.txt",
                "Symbol boxes use YOLO class_id center_x center_y width height, normalized to the included image.\n"
                "classes.json maps IDs to symbol codes/names. OCR and relationships are in annotations/*.json.\n"
                "This export contains one page; create a separate validation split before training.\n",
            )
        return Response(
            archive_bytes.getvalue(),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{stem}-dataset.zip"'},
        )

    return router
