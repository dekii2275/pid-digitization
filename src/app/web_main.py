"""Temporary, database-free drawing viewer API for the AI Review Workspace."""

from __future__ import annotations

import math
import os
import json
import subprocess
import sys
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pypdfium2 as pdfium
from fastapi import Body, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from PIL import Image, UnidentifiedImageError

APP_ROOT = Path(os.getenv("DRAWING_STORAGE_DIR", "/app/uploads"))
PREVIEW_ROOT = Path(os.getenv("PREVIEW_DIR", "/app/previews"))
TILE_ROOT = Path(os.getenv("TILE_DIR", "/app/tiles"))
PIPELINE_ARTIFACTS_ROOT = Path(os.getenv("PIPELINE_ARTIFACTS_DIR", "/app/artifacts/pipeline"))
PIPELINE_WEIGHTS = Path(os.getenv("PIPELINE_WEIGHTS", "/app/models/symbol-detector/best.pt"))
PIPELINE_DEVICE = os.getenv("PIPELINE_DEVICE", "cpu")
PIPELINE_OCR_DEVICE = os.getenv("PIPELINE_OCR_DEVICE", "cpu")
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(100 * 1024 * 1024)))
TILE_SIZE = 512
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
    rendered_pages: dict[int, Path] = field(default_factory=dict)


@dataclass
class PipelineJob:
    job_id: str
    drawing_id: str
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

app = FastAPI(title="VPI P&ID Drawing Viewer", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:18731", "http://127.0.0.1:18731"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def record_or_404(drawing_id: str) -> DrawingRecord:
    record = drawings.get(drawing_id)
    if not record:
        raise HTTPException(404, "Drawing is not available. Upload it again after a service restart.")
    return record


def page_image(record: DrawingRecord, page_number: int) -> Path:
    if not 1 <= page_number <= record.page_count:
        raise HTTPException(404, "Page number is outside this document.")
    cached = record.rendered_pages.get(page_number)
    if cached and cached.exists():
        return cached
    if record.source_type == "image":
        return record.source_path

    output = PREVIEW_ROOT / record.drawing_id / f"page-{page_number}.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        pdf = pdfium.PdfDocument(str(record.source_path))
        bitmap = pdf[page_number - 1].render(scale=2.0)
        bitmap.to_pil().convert("RGB").save(output, "PNG", optimize=True)
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
        "page_count": record.page_count,
        "page_number": 1,
        "width": record.width,
        "height": record.height,
        "tile_size": TILE_SIZE,
        "max_zoom": record.max_zoom,
        "preview_url": f"{base}/preview.jpg",
        "tile_url_template": f"{base}/tiles/{{z}}/{{x}}/{{y}}.png",
        "created_at": record.created_at,
    }


def save_preview(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as image:
        preview = image.convert("RGB")
        preview.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
        preview.save(destination, "JPEG", quality=88, optimize=True)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "storage": "memory-metadata"}


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
                    raise HTTPException(413, f"Tệp vượt giới hạn {MAX_UPLOAD_BYTES // 1024 // 1024} MB.")
                output.write(chunk)

        if extension == ".pdf":
            pdf = pdfium.PdfDocument(str(source_path))
            page_count = len(pdf)
            if page_count == 0:
                raise ValueError("PDF không có trang")
            rendered = PREVIEW_ROOT / drawing_id / "page-1.png"
            rendered.parent.mkdir(parents=True, exist_ok=True)
            bitmap = pdf[0].render(scale=2.0)
            bitmap.to_pil().convert("RGB").save(rendered, "PNG", optimize=True)
            width, height = Image.open(rendered).size
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
        )
        preview_path = PREVIEW_ROOT / drawing_id / "preview.jpg"
        save_preview(page_image(record, 1), preview_path)
        drawings[drawing_id] = record
        return drawing_payload(record)
    except HTTPException:
        source_path.unlink(missing_ok=True)
        raise
    except (UnidentifiedImageError, ValueError, RuntimeError) as error:
        source_path.unlink(missing_ok=True)
        raise HTTPException(422, f"Không thể đọc bản vẽ: {error}") from error
    finally:
        await file.close()


@app.get("/api/v1/documents/{drawing_id}")
def get_document(drawing_id: str) -> dict:
    return drawing_payload(record_or_404(drawing_id))


def job_payload(job: PipelineJob) -> dict:
    return {
        "job_id": job.job_id,
        "drawing_id": job.drawing_id,
        "status": job.status,
        "stage": job.stage,
        "progress": job.progress,
        "error_message": job.error_message,
        "log_tail": job.log_lines[-20:] if job.status == "FAILED" else [],
        "results_url": f"/api/v1/jobs/{job.job_id}/results" if job.status == "COMPLETED" else None,
        "final_results_url": f"/api/v1/jobs/{job.job_id}/final-results" if job.final_result_path else None,
        "final_saved_at": job.final_saved_at,
    }


def update_job(job: PipelineJob, *, status: str | None = None, stage: str | None = None, progress: int | None = None) -> None:
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
    """Run the existing local CLI pipeline in a background thread, without a database."""
    output_dir = PIPELINE_ARTIFACTS_ROOT / drawing.drawing_id / job.job_id
    job.output_dir = output_dir
    try:
        if not PIPELINE_WEIGHTS.is_file():
            raise FileNotFoundError(f"Không tìm thấy trọng số detector: {PIPELINE_WEIGHTS}")
        source = page_image(drawing, 1) if drawing.source_type == "pdf" else drawing.source_path
        script = Path("/app/training/yolov8s/run_pid_pipeline.py")
        if not script.is_file():
            raise FileNotFoundError("Không tìm thấy script pipeline trong container.")
        command = [
            sys.executable, str(script), "--source", str(source), "--weights", str(PIPELINE_WEIGHTS),
            "--output-dir", str(output_dir), "--device", PIPELINE_DEVICE, "--ocr-device", PIPELINE_OCR_DEVICE,
            "--build-editor",
        ]
        update_job(job, status="RUNNING", stage="STARTING", progress=4)
        environment = {**os.environ, "PYTHONPATH": "/app/src"}
        process = subprocess.Popen(
            command, cwd="/app", env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
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
        job.result_path = result_path
        update_job(job, status="COMPLETED", stage="COMPLETED", progress=100)
    except Exception as error:  # Surface a safe, actionable error to the review workspace.
        with jobs_lock:
            job.status = "FAILED"
            job.stage = "FAILED"
            job.error_message = str(error)


@app.post("/api/v1/documents/{drawing_id}/run-all", status_code=202)
def run_all(drawing_id: str) -> dict:
    drawing = record_or_404(drawing_id)
    job = PipelineJob(job_id=f"job_{uuid.uuid4().hex[:12]}", drawing_id=drawing_id)
    with jobs_lock:
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
        raise HTTPException(404, "KhÃ´ng tÃ¬m tháº¥y job.")
    if not job.final_result_path or not job.final_result_path.is_file():
        raise HTTPException(404, "Job nÃ y chÆ°a cÃ³ káº¿t quáº£ review Ä‘Æ°á»£c lÆ°u.")
    return json.loads(job.final_result_path.read_text(encoding="utf-8"))


@app.post("/api/v1/jobs/{job_id}/final-results")
def save_final_results(job_id: str, scene: dict = Body(...)) -> dict:
    """Persist a reviewer-approved copy without overwriting the raw AI scene."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "KhÃ´ng tÃ¬m tháº¥y job.")
    if job.status != "COMPLETED" or not job.result_path:
        raise HTTPException(409, "Pipeline chÆ°a hoÃ n táº¥t.")

    expected_collections = ("symbols", "texts", "lines", "topology_edges")
    if not all(isinstance(scene.get(name), list) for name in expected_collections):
        raise HTTPException(422, "Review scene pháº£i bao gá»“m symbols, texts, lines vÃ  topology_edges.")

    # A JSON round trip detaches the request object and guarantees a serializable
    # final artifact. The raw scene.json is intentionally retained for audit.
    saved_scene = json.loads(json.dumps(scene, ensure_ascii=False))
    saved_at = datetime.now(timezone.utc).isoformat()
    saved_scene["review"] = {
        **(saved_scene.get("review") if isinstance(saved_scene.get("review"), dict) else {}),
        "status": "FINAL",
        "saved_at": saved_at,
    }
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
    preview_name = "preview.jpg" if page_number == 1 else f"preview-{page_number}.jpg"
    preview = PREVIEW_ROOT / drawing_id / preview_name
    if not preview.exists():
        save_preview(page_image(record, page_number), preview)
    return FileResponse(preview, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=3600"})


@app.get("/api/v1/documents/{drawing_id}/pages/{page_number}/tiles/{zoom}/{tile_x}/{tile_y}.png")
def get_tile(drawing_id: str, page_number: int, zoom: int, tile_x: int, tile_y: int) -> FileResponse:
    record = record_or_404(drawing_id)
    if zoom < 0 or zoom > record.max_zoom or tile_x < 0 or tile_y < 0:
        raise HTTPException(404, "Tile không tồn tại.")
    scale_down = 2 ** (record.max_zoom - zoom)
    level_width = math.ceil(record.width / scale_down)
    level_height = math.ceil(record.height / scale_down)
    tiles_x = math.ceil(level_width / TILE_SIZE)
    tiles_y = math.ceil(level_height / TILE_SIZE)
    if tile_x >= tiles_x or tile_y >= tiles_y:
        raise HTTPException(404, "Tile không tồn tại.")

    destination = TILE_ROOT / drawing_id / str(page_number) / str(zoom) / f"{tile_x}-{tile_y}.png"
    if not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        left = tile_x * TILE_SIZE * scale_down
        top = tile_y * TILE_SIZE * scale_down
        right = min(left + TILE_SIZE * scale_down, record.width)
        bottom = min(top + TILE_SIZE * scale_down, record.height)
        with Image.open(page_image(record, page_number)) as image:
            tile = image.convert("RGB").crop((left, top, right, bottom))
            if scale_down > 1:
                tile = tile.resize((math.ceil(tile.width / scale_down), math.ceil(tile.height / scale_down)), Image.Resampling.LANCZOS)
            tile.save(destination, "PNG", optimize=True)
    return FileResponse(destination, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})
