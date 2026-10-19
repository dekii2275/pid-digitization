"""Drawing review API with MinIO files, PostgreSQL metadata and a local AI pipeline."""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import sys
import threading
import uuid
from contextlib import asynccontextmanager, closing
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import pypdfium2 as pdfium
from fastapi import Body, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from minio.error import S3Error
from PIL import Image, UnidentifiedImageError
from psycopg import Error as DatabaseError
from pydantic import BaseModel, ConfigDict, Field, field_validator
from urllib3.exceptions import HTTPError as StorageConnectionError

from app import asset_catalog, document_storage, drawing_editor
from app.annotations import create_router as create_annotation_router
from app.symbol_library import init_library
from app.symbol_library import router as symbol_library_router

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = Path(os.getenv("DRAWING_STORAGE_DIR", str(REPO_ROOT / "uploads")))
PREVIEW_ROOT = Path(os.getenv("PREVIEW_DIR", str(REPO_ROOT / "artifacts/previews")))
TILE_ROOT = Path(os.getenv("TILE_DIR", str(REPO_ROOT / "artifacts/tiles")))
PIPELINE_ARTIFACTS_ROOT = Path(
    os.getenv("PIPELINE_ARTIFACTS_DIR", str(REPO_ROOT / "artifacts/pipeline"))
)
PIPELINE_WEIGHTS = Path(
    os.getenv("PIPELINE_WEIGHTS", str(REPO_ROOT / "models/symbol-detector/best.pt"))
)
PIPELINE_DEVICE = os.getenv("PIPELINE_DEVICE", "cpu")
PIPELINE_OCR_DEVICE = os.getenv("PIPELINE_OCR_DEVICE", "cpu")
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(100 * 1024 * 1024)))
TILE_SIZE = 512
PDF_RENDER_DPI = 144
PDF_MAX_RENDER_PIXELS = 16_000_000
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".pdf"}

for directory in (APP_ROOT, PREVIEW_ROOT, TILE_ROOT, PIPELINE_ARTIFACTS_ROOT):
    directory.mkdir(parents=True, exist_ok=True)


@dataclass
class DrawingRecord:
    drawing_id: str
    original_name: str
    source_path: Path
    source_type: str
    page_count: int
    width: int
    height: int
    max_zoom: int
    created_at: str
    bucket: str = ""
    object_key: str = ""
    byte_size: int = 0
    sha256: str = ""
    annotation_count: int = 0
    labeled_pages: list[int] = field(default_factory=list)
    last_labeled_at: str | None = None
    project: str = ""
    drawing_set: str = ""
    drawing_number: str = ""
    revision_label: str = ""
    lifecycle: str = "current"
    tags: list[str] = field(default_factory=list)
    updated_at: str | None = None
    page_workflows: dict = field(default_factory=dict)
    completed_page_count: int = 0
    rendered_pages: dict[int, Path] = field(default_factory=dict)
    # Old documents must keep their 144-DPI coordinate system after restart.
    render_dpi: int = 144
    render_max_pixels: int | None = None


@dataclass
class PipelineJob:
    job_id: str
    drawing_id: str
    page_number: int = 1
    status: str = "QUEUED"
    stage: str = "QUEUED"
    progress: int = 0
    error_message: str | None = None
    output_dir: Path | None = None
    result_path: Path | None = None
    final_result_path: Path | None = None
    final_saved_at: str | None = None
    log_lines: list[str] = field(default_factory=list)


drawings: dict[str, DrawingRecord] = {}
jobs: dict[str, PipelineJob] = {}
jobs_lock = threading.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_library()
    document_storage.init_documents(APP_ROOT)
    drawing_editor.import_legacy_results(PIPELINE_ARTIFACTS_ROOT)
    yield


app = FastAPI(title="VPI P&ID Drawing Viewer", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv(
        "CORS_ORIGINS",
        "http://localhost:18731,http://127.0.0.1:18731,http://localhost:18180,http://127.0.0.1:18180",
    ).split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(symbol_library_router)
app.include_router(asset_catalog.router)


async def storage_unavailable(request, error):
    return JSONResponse(
        status_code=503, content={"detail": "Không thể kết nối kho bản vẽ. Vui lòng thử lại sau."}
    )


for error_type in (DatabaseError, S3Error, StorageConnectionError):
    app.add_exception_handler(error_type, storage_unavailable)


def record_from_metadata(data: dict) -> DrawingRecord:
    return DrawingRecord(
        source_path=APP_ROOT / f"{data['drawing_id']}{data['extension']}",
        **{key: value for key, value in data.items() if key in DrawingRecord.__dataclass_fields__},
    )


def record_or_404(drawing_id: str) -> DrawingRecord:
    if not re.fullmatch(r"[a-f0-9]{32}", drawing_id):
        raise HTTPException(404, "Không tìm thấy bản vẽ.")
    data = document_storage.get_document(drawing_id)
    if not data:
        raise HTTPException(404, "Không tìm thấy bản vẽ.")
    record = record_from_metadata(data)
    drawings[drawing_id] = record
    return record


def pdf_render_scale(page, dpi: int, max_pixels: int | None) -> float:
    width, height = page.get_size()
    if width <= 0 or height <= 0:
        raise ValueError("Kích thước trang PDF không hợp lệ")
    scale = dpi / 72
    if max_pixels and math.ceil(width * scale) * math.ceil(height * scale) > max_pixels:
        # PDFium rounds both dimensions up; include that rounding in the limit.
        low, high = 0.0, scale
        for _ in range(40):
            middle = (low + high) / 2
            if math.ceil(width * middle) * math.ceil(height * middle) <= max_pixels:
                low = middle
            else:
                high = middle
        scale = low
    return scale


def render_pdf_page(page, output: Path, dpi: int, max_pixels: int | None) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    scale = pdf_render_scale(page, dpi, max_pixels)
    temporary = output.with_name(f"{output.stem}-{uuid.uuid4().hex}.tmp")
    try:
        with closing(page.render(scale=scale)) as bitmap:
            with bitmap.to_pil().convert("RGB") as image:
                image.save(temporary, "PNG", dpi=(scale * 72, scale * 72))
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)


def page_image(record: DrawingRecord, page_number: int) -> Path:
    if not 1 <= page_number <= record.page_count:
        raise HTTPException(404, "Page number is outside this document.")
    cached = record.rendered_pages.get(page_number)
    if cached and cached.exists():
        return cached
    if record.source_type == "image":
        return document_storage.cache_source(vars(record), record.source_path)

    output = PREVIEW_ROOT / record.drawing_id / f"page-{page_number}.png"
    try:
        if not output.exists():
            document_storage.cache_source(vars(record), record.source_path)
            with closing(pdfium.PdfDocument(str(record.source_path))) as pdf:
                with closing(pdf[page_number - 1]) as page:
                    render_pdf_page(page, output, record.render_dpi, record.render_max_pixels)
    except (HTTPException, DatabaseError, S3Error, StorageConnectionError):
        raise
    except Exception as error:  # pragma: no cover - defensive response for malformed PDFs
        raise HTTPException(422, f"Không thể render trang PDF: {error}") from error
    record.rendered_pages[page_number] = output
    return output


def drawing_payload(record: DrawingRecord) -> dict:
    base = f"/api/v1/documents/{record.drawing_id}/pages/1"
    return {
        "id": record.drawing_id,
        "name": record.original_name,
        "source_type": record.source_type,
        "render_dpi": record.render_dpi if record.source_type == "pdf" else None,
        "page_count": record.page_count,
        "page_number": 1,
        "width": record.width,
        "height": record.height,
        "tile_size": TILE_SIZE,
        "max_zoom": record.max_zoom,
        "preview_url": f"{base}/preview.jpg",
        "tile_url_template": f"{base}/tiles/{{z}}/{{x}}/{{y}}.png",
        "created_at": record.created_at,
        "byte_size": record.byte_size,
        "file_path": f"s3://{record.bucket}/{record.object_key}",
        "original_url": f"/api/v1/documents/{record.drawing_id}/original",
        "is_labeled": record.annotation_count > 0,
        "annotation_count": record.annotation_count,
        "labeled_pages": record.labeled_pages,
        "last_labeled_at": record.last_labeled_at,
        "project": record.project,
        "drawing_set": record.drawing_set,
        "drawing_number": record.drawing_number,
        "revision_label": record.revision_label,
        "lifecycle": record.lifecycle,
        "tags": record.tags,
        "updated_at": record.updated_at or record.created_at,
        "page_workflows": record.page_workflows,
        "completed_page_count": record.completed_page_count,
    }


app.include_router(create_annotation_router(record_or_404, page_image, repository=document_storage))


@app.get("/api/v1/documents")
def list_documents(labeled: bool | None = None) -> list[dict]:
    return [
        drawing_payload(record_from_metadata(data))
        for data in document_storage.list_documents(labeled)
    ]


class DocumentOrganizationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project: str = Field(max_length=120)
    drawing_set: str = Field(max_length=120)
    tags: list[str] = Field(max_length=30)
    drawing_number: str = Field(default="", max_length=120)
    revision_label: str = Field(default="", max_length=60)
    lifecycle: Literal["current", "superseded"] = "current"

    @field_validator("project", "drawing_set", "drawing_number", "revision_label")
    @classmethod
    def trim_name(cls, value):
        return value.strip()

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, values):
        result = []
        for value in values:
            tag = value.strip()
            if not tag or len(tag) > 60:
                raise ValueError("Tag phải có từ 1 đến 60 ký tự.")
            if tag.casefold() not in {item.casefold() for item in result}:
                result.append(tag)
        return result


class PageStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["not_started", "in_progress", "pending_review", "completed"]
    revision: int = Field(ge=0)
    annotation_revision: int = Field(ge=0)


@app.patch("/api/v1/documents/{drawing_id}")
def organize_document(drawing_id: str, request: DocumentOrganizationRequest) -> dict:
    record_or_404(drawing_id)
    document_storage.update_document(drawing_id, request.model_dump(exclude_unset=True))
    return drawing_payload(record_or_404(drawing_id))


@app.put("/api/v1/documents/{drawing_id}/pages/{page_number}/status")
def update_page_status(drawing_id: str, page_number: int, request: PageStatusRequest) -> dict:
    record_or_404(drawing_id)
    document_storage.save_page_status(
        drawing_id, page_number, request.status, request.revision, request.annotation_revision
    )
    return drawing_payload(record_or_404(drawing_id))


@app.get("/api/v1/documents/{drawing_id}/pages/{page_number}/thumbnail.jpg")
def get_page_thumbnail(drawing_id: str, page_number: int) -> FileResponse:
    record = record_or_404(drawing_id)
    if not 1 <= page_number <= record.page_count:
        raise HTTPException(404, "Trang không thuộc bản vẽ.")
    output = PREVIEW_ROOT / drawing_id / f"thumbnail-{page_number}.jpg"
    if not output.exists():
        output.parent.mkdir(parents=True, exist_ok=True)
        source = document_storage.cache_source(vars(record), record.source_path)
        temporary = output.with_name(f"{output.stem}-{uuid.uuid4().hex}.tmp")
        try:
            if record.source_type == "pdf":
                with closing(pdfium.PdfDocument(str(source))) as pdf:
                    with closing(pdf[page_number - 1]) as page:
                        with closing(
                            page.render(scale=pdf_render_scale(page, 36, 160_000))
                        ) as bitmap:
                            with bitmap.to_pil().convert("RGB") as image:
                                image.thumbnail((320, 320), Image.Resampling.LANCZOS)
                                image.save(temporary, "JPEG", quality=80)
            else:
                with Image.open(source) as original:
                    with original.convert("RGB") as image:
                        image.thumbnail((320, 320), Image.Resampling.LANCZOS)
                        image.save(temporary, "JPEG", quality=80)
            temporary.replace(output)
        finally:
            temporary.unlink(missing_ok=True)
    return FileResponse(output, media_type="image/jpeg")


@app.get("/api/v1/documents/{drawing_id}/pages/{page_number}")
def get_document_page(drawing_id: str, page_number: int) -> dict:
    record = record_or_404(drawing_id)
    with Image.open(page_image(record, page_number)) as image:
        width, height = image.size
    base = f"/api/v1/documents/{drawing_id}/pages/{page_number}"
    return {
        **drawing_payload(record),
        "page_number": page_number,
        "width": width,
        "height": height,
        "max_zoom": max(0, math.ceil(math.log2(max(width, height) / TILE_SIZE))),
        "preview_url": f"{base}/preview.jpg",
        "tile_url_template": f"{base}/tiles/{{z}}/{{x}}/{{y}}.png",
    }


def editor_page_context(drawing_id: str, page_number: int) -> dict:
    page = get_document_page(drawing_id, page_number)
    return {
        "drawing_id": drawing_id,
        "page_number": page_number,
        "width": page["width"],
        "height": page["height"],
        "name": page["name"],
    }


app.include_router(drawing_editor.create_router(editor_page_context))


def save_preview(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as image:
        preview = image.convert("RGB")
        preview.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
        preview.save(destination, "JPEG", quality=88, optimize=True)


@app.get("/health")
def health() -> dict:
    with document_storage.connection() as db:
        db.execute("SELECT 1 FROM drawing_documents LIMIT 1")
    if not document_storage.client().bucket_exists(os.getenv("MINIO_BUCKET", "pid-drawings")):
        raise HTTPException(503, "Kho bản vẽ chưa sẵn sàng.")
    return {"status": "ok", "storage": "minio", "metadata": "postgresql"}


@app.post("/api/v1/documents/upload", status_code=201)
async def upload_document(file: UploadFile = File(...)) -> dict:
    original_name = Path(file.filename or "drawing").name
    extension = Path(original_name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(415, "Chỉ hỗ trợ PDF, PNG, JPG hoặc JPEG.")

    drawing_id = uuid.uuid4().hex
    source_path = APP_ROOT / f"{drawing_id}{extension}"
    received = 0
    try:
        with source_path.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                received += len(chunk)
                if received > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        413, f"Tệp vượt giới hạn {MAX_UPLOAD_BYTES // 1024 // 1024} MB."
                    )
                output.write(chunk)

        if extension == ".pdf":
            rendered = PREVIEW_ROOT / drawing_id / "page-1.png"
            with closing(pdfium.PdfDocument(str(source_path))) as pdf:
                page_count = len(pdf)
                if page_count == 0:
                    raise ValueError("PDF không có trang")
                with closing(pdf[0]) as page:
                    render_pdf_page(page, rendered, PDF_RENDER_DPI, PDF_MAX_RENDER_PIXELS)
            with Image.open(rendered) as image:
                width, height = image.size
            source_type = "pdf"
            rendered_pages = {1: rendered}
        else:
            with Image.open(source_path) as image:
                width, height = image.size
                image.verify()
            page_count = 1
            source_type = "image"
            rendered_pages = {}

        if width < 32 or height < 32:
            raise ValueError("Kích thước ảnh quá nhỏ để xem bản vẽ")
        max_zoom = max(0, math.ceil(math.log2(max(width, height) / TILE_SIZE)))
        record = DrawingRecord(
            drawing_id=drawing_id,
            original_name=original_name,
            source_path=source_path,
            source_type=source_type,
            page_count=page_count,
            width=width,
            height=height,
            max_zoom=max_zoom,
            created_at=datetime.now(timezone.utc).isoformat(),
            rendered_pages=rendered_pages,
            render_dpi=PDF_RENDER_DPI if source_type == "pdf" else 144,
            render_max_pixels=PDF_MAX_RENDER_PIXELS if source_type == "pdf" else None,
        )
        preview_path = PREVIEW_ROOT / drawing_id / "preview.jpg"
        save_preview(page_image(record, 1), preview_path)
        metadata = {
            "extension": extension,
            **{
                key: getattr(record, key)
                for key in (
                    "original_name",
                    "source_type",
                    "page_count",
                    "width",
                    "height",
                    "max_zoom",
                    "created_at",
                    "render_dpi",
                    "render_max_pixels",
                )
            },
        }
        stored = document_storage.save_source(drawing_id, source_path, metadata)
        record = record_from_metadata(stored)
        source_path.unlink(missing_ok=True)
        drawings[drawing_id] = record
        return drawing_payload(record)
    except (UnidentifiedImageError, ValueError, RuntimeError) as error:
        raise HTTPException(422, f"Không thể đọc bản vẽ: {error}") from error
    finally:
        source_path.unlink(missing_ok=True)
        if drawing_id not in drawings:
            shutil.rmtree(PREVIEW_ROOT / drawing_id, ignore_errors=True)
        await file.close()


@app.get("/api/v1/documents/{drawing_id}")
def get_document(drawing_id: str) -> dict:
    return drawing_payload(record_or_404(drawing_id))


@app.get("/api/v1/documents/{drawing_id}/original")
def get_original(drawing_id: str) -> FileResponse:
    record = record_or_404(drawing_id)
    path = document_storage.cache_source(vars(record), record.source_path)
    return FileResponse(path, filename=record.original_name)


@app.delete("/api/v1/documents/{drawing_id}")
def delete_document(drawing_id: str) -> dict:
    record = record_or_404(drawing_id)
    with jobs_lock:
        if any(
            job.drawing_id == drawing_id and job.status in {"QUEUED", "RUNNING"}
            for job in jobs.values()
        ):
            raise HTTPException(
                409, "Bản vẽ đang được xử lý. Hãy đợi pipeline hoàn tất trước khi xóa."
            )
        document_storage.delete_document(drawing_id)
        for job_id in [key for key, job in jobs.items() if job.drawing_id == drawing_id]:
            del jobs[job_id]
    drawings.pop(drawing_id, None)
    record.source_path.unlink(missing_ok=True)
    (APP_ROOT / f"{drawing_id}.json").unlink(missing_ok=True)
    for root in (PREVIEW_ROOT, TILE_ROOT, PIPELINE_ARTIFACTS_ROOT, APP_ROOT / "annotations"):
        shutil.rmtree(root / drawing_id, ignore_errors=True)
    return {"deleted": drawing_id}


def job_payload(job: PipelineJob) -> dict:
    return {
        "job_id": job.job_id,
        "drawing_id": job.drawing_id,
        "page_number": job.page_number,
        "status": job.status,
        "stage": job.stage,
        "progress": job.progress,
        "error_message": job.error_message,
        "log_tail": job.log_lines[-20:] if job.status == "FAILED" else [],
        "results_url": f"/api/v1/jobs/{job.job_id}/results" if job.status == "COMPLETED" else None,
        "final_results_url": f"/api/v1/jobs/{job.job_id}/final-results"
        if job.final_result_path
        else None,
        "final_saved_at": job.final_saved_at,
    }


def update_job(
    job: PipelineJob,
    *,
    status: str | None = None,
    stage: str | None = None,
    progress: int | None = None,
) -> None:
    with jobs_lock:
        if status is not None:
            job.status = status
        if stage is not None:
            job.stage = stage
        if progress is not None:
            job.progress = progress


def pipeline_progress_from_line(line: str) -> tuple[str, int] | None:
    lower = line.lower()
    if "tiled_inference.py" in lower:
        return ("DETECTING_SYMBOLS", 12)
    if "ocr_baseline.py" in lower:
        return ("OCR_TAGS", 36)
    if "line_detection_baseline.py" in lower:
        return ("DETECTING_LINES", 60)
    if "topology_adapter.py" in lower:
        return ("BUILDING_TOPOLOGY", 80)
    if "build_editable_scene.py" in lower:
        return ("PREPARING_REVIEW_SCENE", 92)
    return None


def run_pipeline_job(job: PipelineJob, drawing: DrawingRecord) -> None:
    """Run the local CLI pipeline in a background thread."""
    output_dir = PIPELINE_ARTIFACTS_ROOT / drawing.drawing_id / job.job_id
    job.output_dir = output_dir
    try:
        if not PIPELINE_WEIGHTS.is_file():
            raise FileNotFoundError(f"Không tìm thấy trọng số detector: {PIPELINE_WEIGHTS}")
        source = page_image(drawing, job.page_number)
        script = REPO_ROOT / "training/yolov8s/run_pid_pipeline.py"
        if not script.is_file():
            raise FileNotFoundError("Không tìm thấy script pipeline trong container.")
        command = [
            sys.executable,
            str(script),
            "--source",
            str(source),
            "--weights",
            str(PIPELINE_WEIGHTS),
            "--output-dir",
            str(output_dir),
            "--device",
            PIPELINE_DEVICE,
            "--ocr-device",
            PIPELINE_OCR_DEVICE,
            "--build-editor",
        ]
        update_job(job, status="RUNNING", stage="STARTING", progress=4)
        environment = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "src"), "PYTHONUNBUFFERED": "1"}
        process = subprocess.Popen(
            command,
            cwd=REPO_ROOT,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert process.stdout is not None
        for line in process.stdout:
            with jobs_lock:
                job.log_lines.append(line.rstrip())
                del job.log_lines[:-80]
            event = pipeline_progress_from_line(line)
            if event:
                update_job(job, stage=event[0], progress=event[1])
        if process.wait() != 0:
            raise RuntimeError(f"Pipeline kết thúc với mã lỗi {process.returncode}.")
        result_path = output_dir / "editor" / "scene.json"
        if not result_path.is_file():
            raise FileNotFoundError("Pipeline không tạo được editor/scene.json.")
        (output_dir / "page-context.json").write_text(
            json.dumps({"page_number": job.page_number}), encoding="utf-8"
        )
        drawing_editor.save_processed_scene(
            drawing.drawing_id,
            job.page_number,
            job.job_id,
            json.loads(result_path.read_text(encoding="utf-8")),
        )
        job.result_path = result_path
        update_job(job, status="COMPLETED", stage="COMPLETED", progress=100)
    except Exception as error:  # Surface a safe, actionable error to the review workspace.
        with jobs_lock:
            job.status = "FAILED"
            job.stage = "FAILED"
            job.error_message = str(error)


@app.post("/api/v1/documents/{drawing_id}/run-all", status_code=202)
def run_all(drawing_id: str, page_number: int = Query(default=1, ge=1)) -> dict:
    with jobs_lock:
        drawing = record_or_404(drawing_id)
        if page_number > drawing.page_count:
            raise HTTPException(404, "Trang không thuộc bản vẽ.")
        job = PipelineJob(
            job_id=f"job_{uuid.uuid4().hex[:12]}", drawing_id=drawing_id, page_number=page_number
        )
        jobs[job.job_id] = job
    threading.Thread(target=run_pipeline_job, args=(job, drawing), daemon=True).start()
    return job_payload(job)


@app.get("/api/v1/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Không tìm thấy job.")
    return job_payload(job)


@app.get("/api/v1/jobs/{job_id}/results")
def get_job_results(job_id: str) -> dict:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Không tìm thấy job.")
    if job.status != "COMPLETED" or not job.result_path:
        raise HTTPException(409, "Pipeline chưa hoàn tất.")
    return json.loads(job.result_path.read_text(encoding="utf-8"))


@app.get("/api/v1/jobs/{job_id}/final-results")
def get_final_results(job_id: str) -> dict:
    """Return the latest reviewer-approved scene for a completed pipeline job."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Không tìm thấy job.")
    if not job.final_result_path or not job.final_result_path.is_file():
        raise HTTPException(404, "Job này chưa có kết quả review được lưu.")
    return json.loads(job.final_result_path.read_text(encoding="utf-8"))


@app.post("/api/v1/jobs/{job_id}/final-results")
def save_final_results(job_id: str, scene: dict = Body(...)) -> dict:
    """Persist a reviewer-approved copy without overwriting the raw AI scene."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Không tìm thấy job.")
    if job.status != "COMPLETED" or not job.result_path:
        raise HTTPException(409, "Pipeline chưa hoàn tất.")

    expected_collections = ("symbols", "texts", "lines", "topology_edges")
    if not all(isinstance(scene.get(name), list) for name in expected_collections):
        raise HTTPException(
            422, "Review scene phải bao gồm symbols, texts, lines và topology_edges."
        )

    # A JSON round trip detaches the request object and guarantees a serializable
    # final artifact. The raw scene.json is intentionally retained for audit.
    saved_scene = json.loads(json.dumps(scene, ensure_ascii=False))
    saved_at = datetime.now(timezone.utc).isoformat()
    saved_scene["review"] = {
        **(saved_scene.get("review") if isinstance(saved_scene.get("review"), dict) else {}),
        "status": "FINAL",
        "saved_at": saved_at,
    }
    asset_catalog.save_review_scene(job.drawing_id, job_id, saved_scene, job.page_number)
    destination = job.result_path.with_name("final-scene.json")
    temporary = destination.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(saved_scene, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(destination)
    with jobs_lock:
        job.final_result_path = destination
        job.final_saved_at = saved_at
    return {"saved_at": saved_at, "result": saved_scene}


@app.get("/api/v1/documents/{drawing_id}/pages/{page_number}/preview.jpg")
def get_preview(drawing_id: str, page_number: int) -> FileResponse:
    record = record_or_404(drawing_id)
    if not 1 <= page_number <= record.page_count:
        raise HTTPException(404, "Page number is outside this document.")
    preview_name = "preview.jpg" if page_number == 1 else f"preview-{page_number}.jpg"
    preview = PREVIEW_ROOT / drawing_id / preview_name
    if not preview.exists():
        save_preview(page_image(record, page_number), preview)
    return FileResponse(
        preview, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=3600"}
    )


@app.get("/api/v1/documents/{drawing_id}/pages/{page_number}/tiles/{zoom}/{tile_x}/{tile_y}.png")
def get_tile(
    drawing_id: str, page_number: int, zoom: int, tile_x: int, tile_y: int
) -> FileResponse:
    record = record_or_404(drawing_id)
    if not 1 <= page_number <= record.page_count:
        raise HTTPException(404, "Page number is outside this document.")
    image_path = page_image(record, page_number)
    with Image.open(image_path) as image:
        width, height = image.size
    max_zoom = max(0, math.ceil(math.log2(max(width, height) / TILE_SIZE)))
    if zoom < 0 or zoom > max_zoom or tile_x < 0 or tile_y < 0:
        raise HTTPException(404, "Tile không tồn tại.")
    scale_down = 2 ** (max_zoom - zoom)
    level_width = math.ceil(width / scale_down)
    level_height = math.ceil(height / scale_down)
    tiles_x = math.ceil(level_width / TILE_SIZE)
    tiles_y = math.ceil(level_height / TILE_SIZE)
    if tile_x >= tiles_x or tile_y >= tiles_y:
        raise HTTPException(404, "Tile không tồn tại.")

    destination = TILE_ROOT / drawing_id / str(page_number) / str(zoom) / f"{tile_x}-{tile_y}.png"
    if not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        left = tile_x * TILE_SIZE * scale_down
        top = tile_y * TILE_SIZE * scale_down
        right = min(left + TILE_SIZE * scale_down, width)
        bottom = min(top + TILE_SIZE * scale_down, height)
        with Image.open(image_path) as image:
            tile = image.crop((left, top, right, bottom)).convert("RGB")
            if scale_down > 1:
                tile = tile.resize(
                    (math.ceil(tile.width / scale_down), math.ceil(tile.height / scale_down)),
                    Image.Resampling.LANCZOS,
                )
            tile.save(destination, "PNG", optimize=True)
    return FileResponse(
        destination, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"}
    )
