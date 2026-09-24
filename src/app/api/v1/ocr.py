"""API routes for OCR texts management and editing."""

from __future__ import annotations

from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.db.models import OcrText
from app.db.repositories.drawing_repository import DrawingRepository
from app.schemas import OcrResponse, OcrUpdate

router = APIRouter(prefix="", tags=["ocr"])


@router.get("/drawings/{drawing_id}/ocr", response_model=List[OcrResponse])
def get_drawing_ocr(
    drawing_id: int,
    search: str = Query("", description="Search text query"),
    db: Session = Depends(get_db),
):
    """Get all OCR texts for a drawing with optional search query."""
    query = db.query(OcrText).filter(OcrText.drawing_id == drawing_id)
    if search:
        query = query.filter(OcrText.text.ilike(f"%{search}%"))
    return query.all()


@router.put("/ocr/{ocr_id}", response_model=OcrResponse)
def update_ocr(ocr_id: int, payload: OcrUpdate, db: Session = Depends(get_db)):
    """Update OCR text content or associated symbol and record revision."""
    repo = DrawingRepository(db)
    ocr = db.query(OcrText).filter(OcrText.id == ocr_id).first()
    if not ocr:
        raise HTTPException(status_code=404, detail="OCR record not found")

    before_state = {"text": ocr.text, "associated_symbol_id": ocr.associated_symbol_id}

    if payload.text is not None:
        ocr.text = payload.text
    if payload.associated_symbol_id is not None:
        ocr.associated_symbol_id = payload.associated_symbol_id

    ocr.source = "USER"
    db.commit()
    db.refresh(ocr)

    after_state = {"text": ocr.text, "associated_symbol_id": ocr.associated_symbol_id}

    repo.record_revision(
        drawing_id=ocr.drawing_id,
        entity_type="ocr",
        entity_id=ocr.id,
        action="UPDATE",
        before_state=before_state,
        after_state=after_state,
    )
    return ocr
