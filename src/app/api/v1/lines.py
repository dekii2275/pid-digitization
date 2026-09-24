"""API routes for detected lines and polyline geometry."""

from __future__ import annotations

from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.db.models import DetectedLine
from app.db.repositories.drawing_repository import DrawingRepository
from app.schemas import LineResponse, LineUpdate

router = APIRouter(prefix="", tags=["lines"])


@router.get("/drawings/{drawing_id}/lines", response_model=List[LineResponse])
def get_drawing_lines(drawing_id: int, db: Session = Depends(get_db)):
    """Get all detected lines for a drawing."""
    return db.query(DetectedLine).filter(DetectedLine.drawing_id == drawing_id).all()


@router.put("/lines/{line_id}", response_model=LineResponse)
def update_line(line_id: int, payload: LineUpdate, db: Session = Depends(get_db)):
    """Update line geometry or type and record revision."""
    repo = DrawingRepository(db)
    line = db.query(DetectedLine).filter(DetectedLine.id == line_id).first()
    if not line:
        raise HTTPException(status_code=404, detail="Line not found")

    before_state = {
        "line_type": line.line_type,
        "geometry": line.geometry,
        "flow_direction": line.flow_direction,
    }

    if payload.line_type is not None:
        line.line_type = payload.line_type
    if payload.geometry is not None:
        line.geometry = payload.geometry
    if payload.flow_direction is not None:
        line.flow_direction = payload.flow_direction

    line.source = "USER"
    db.commit()
    db.refresh(line)

    after_state = {
        "line_type": line.line_type,
        "geometry": line.geometry,
        "flow_direction": line.flow_direction,
    }

    repo.record_revision(
        drawing_id=line.drawing_id,
        entity_type="line",
        entity_id=line.id,
        action="UPDATE",
        before_state=before_state,
        after_state=after_state,
    )
    return line
