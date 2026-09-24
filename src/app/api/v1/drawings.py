"""API routes for P&ID drawings management and file upload."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session
from PIL import Image

from app.core.config import settings
from app.core.database import get_db
from app.db.repositories.drawing_repository import DrawingRepository
from app.schemas import DrawingResponse

router = APIRouter(prefix="/drawings", tags=["drawings"])


@router.post("/upload", response_model=DrawingResponse)
async def upload_drawing(
    file: UploadFile = File(...),
    name: Optional[str] = Form(None),
    project_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
):
    """Upload a P&ID drawing (image or PDF)."""
    filename = file.filename or "uploaded_drawing"
    stem = Path(filename).stem
    ext = Path(filename).suffix.lower()
    drawing_name = name or stem

    # Determine file type
    file_type = "pdf" if ext == ".pdf" else "image"

    # Save to uploads directory
    target_path = settings.UPLOADS_DIR / filename
    counter = 1
    while target_path.exists():
        target_path = settings.UPLOADS_DIR / f"{stem}_{counter}{ext}"
        counter += 1

    with open(target_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Determine width and height if image
    width, height = None, None
    if file_type == "image":
        try:
            with Image.open(target_path) as img:
                width, height = img.size
        except Exception:
            pass

    repo = DrawingRepository(db)
    drawing = repo.create_drawing(
        name=drawing_name,
        original_filename=filename,
        file_path=str(target_path),
        file_type=file_type,
        project_id=project_id,
        width=width,
        height=height,
    )
    return drawing


@router.get("", response_model=List[DrawingResponse])
def list_drawings(project_id: Optional[int] = None, db: Session = Depends(get_db)):
    repo = DrawingRepository(db)
    return repo.list_drawings(project_id=project_id)


@router.get("/{drawing_id}", response_model=DrawingResponse)
def get_drawing(drawing_id: int, db: Session = Depends(get_db)):
    repo = DrawingRepository(db)
    drawing = repo.get_drawing(drawing_id)
    if not drawing:
        raise HTTPException(status_code=404, detail="Drawing not found")
    return drawing
