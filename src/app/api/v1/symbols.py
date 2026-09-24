"""API routes for detected symbols management and human-in-the-loop editing."""

from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.db.models import DetectedSymbol
from app.db.repositories.drawing_repository import DrawingRepository
from app.schemas import SymbolCreate, SymbolResponse, SymbolUpdate

router = APIRouter(prefix="", tags=["symbols"])


@router.get("/drawings/{drawing_id}/symbols", response_model=List[SymbolResponse])
def get_drawing_symbols(
    drawing_id: int,
    category: Optional[str] = Query(None),
    min_confidence: float = Query(0.0),
    db: Session = Depends(get_db),
):
    """Get all detected symbols for a drawing with optional category and confidence filters."""
    query = db.query(DetectedSymbol).filter(
        DetectedSymbol.drawing_id == drawing_id,
        DetectedSymbol.confidence >= min_confidence,
    )
    if category:
        query = query.filter(DetectedSymbol.category.ilike(category))
    return query.all()


@router.post("/symbols", response_model=SymbolResponse)
def create_symbol(payload: SymbolCreate, db: Session = Depends(get_db)):
    """Manually add a symbol (Human-in-the-loop)."""
    repo = DrawingRepository(db)
    symbol = DetectedSymbol(
        drawing_id=payload.drawing_id,
        page_id=payload.page_id,
        class_name=payload.class_name,
        category=payload.category,
        bbox_x1=payload.bbox_x1,
        bbox_y1=payload.bbox_y1,
        bbox_x2=payload.bbox_x2,
        bbox_y2=payload.bbox_y2,
        confidence=payload.confidence,
        tag=payload.tag,
        source="USER",
    )
    db.add(symbol)
    db.commit()
    db.refresh(symbol)

    repo.record_revision(
        drawing_id=symbol.drawing_id,
        entity_type="symbol",
        entity_id=symbol.id,
        action="CREATE",
        before_state=None,
        after_state={
            "class_name": symbol.class_name,
            "category": symbol.category,
            "bbox": [symbol.bbox_x1, symbol.bbox_y1, symbol.bbox_x2, symbol.bbox_y2],
            "tag": symbol.tag,
        },
    )
    return symbol


@router.put("/symbols/{symbol_id}", response_model=SymbolResponse)
def update_symbol(symbol_id: int, payload: SymbolUpdate, db: Session = Depends(get_db)):
    """Update symbol properties and record revision."""
    repo = DrawingRepository(db)
    symbol = db.query(DetectedSymbol).filter(DetectedSymbol.id == symbol_id).first()
    if not symbol:
        raise HTTPException(status_code=404, detail="Symbol not found")

    before_state = {
        "class_name": symbol.class_name,
        "category": symbol.category,
        "bbox": [symbol.bbox_x1, symbol.bbox_y1, symbol.bbox_x2, symbol.bbox_y2],
        "tag": symbol.tag,
    }

    if payload.class_name is not None:
        symbol.class_name = payload.class_name
    if payload.category is not None:
        symbol.category = payload.category
    if payload.bbox_x1 is not None:
        symbol.bbox_x1 = payload.bbox_x1
    if payload.bbox_y1 is not None:
        symbol.bbox_y1 = payload.bbox_y1
    if payload.bbox_x2 is not None:
        symbol.bbox_x2 = payload.bbox_x2
    if payload.bbox_y2 is not None:
        symbol.bbox_y2 = payload.bbox_y2
    if payload.tag is not None:
        symbol.tag = payload.tag

    symbol.source = "USER"
    db.commit()
    db.refresh(symbol)

    after_state = {
        "class_name": symbol.class_name,
        "category": symbol.category,
        "bbox": [symbol.bbox_x1, symbol.bbox_y1, symbol.bbox_x2, symbol.bbox_y2],
        "tag": symbol.tag,
    }

    repo.record_revision(
        drawing_id=symbol.drawing_id,
        entity_type="symbol",
        entity_id=symbol.id,
        action="UPDATE",
        before_state=before_state,
        after_state=after_state,
    )
    return symbol


@router.delete("/symbols/{symbol_id}")
def delete_symbol(symbol_id: int, db: Session = Depends(get_db)):
    """Delete a symbol and record revision."""
    repo = DrawingRepository(db)
    symbol = db.query(DetectedSymbol).filter(DetectedSymbol.id == symbol_id).first()
    if not symbol:
        raise HTTPException(status_code=404, detail="Symbol not found")

    before_state = {
        "class_name": symbol.class_name,
        "category": symbol.category,
        "bbox": [symbol.bbox_x1, symbol.bbox_y1, symbol.bbox_x2, symbol.bbox_y2],
        "tag": symbol.tag,
    }
    drawing_id = symbol.drawing_id

    db.delete(symbol)
    db.commit()

    repo.record_revision(
        drawing_id=drawing_id,
        entity_type="symbol",
        entity_id=symbol_id,
        action="DELETE",
        before_state=before_state,
        after_state=None,
    )
    return {"message": "Symbol deleted successfully"}
