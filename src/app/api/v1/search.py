"""API routes for smart tag search and relationship querying."""

from __future__ import annotations

from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.db.repositories.drawing_repository import DrawingRepository

router = APIRouter(prefix="/search", tags=["search"])


@router.get("")
def search_by_tag(
    drawing_id: int = Query(..., description="ID of the drawing to search within"),
    tag: str = Query(..., min_length=1, description="Equipment or Instrument Tag (e.g. T-101, P-101, V-102)"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Search for a symbol by tag and find its connected equipment, valves, and instruments."""
    repo = DrawingRepository(db)
    result = repo.search_by_tag(drawing_id=drawing_id, tag=tag)
    if not result.get("found"):
        raise HTTPException(status_code=404, detail=f"No equipment or instrument found matching tag '{tag}'")
    return result
