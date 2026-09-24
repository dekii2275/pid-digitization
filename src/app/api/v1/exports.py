"""API routes for exporting Structured JSON and DEXPI-compatible XML."""

from __future__ import annotations

from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.db.repositories.drawing_repository import DrawingRepository
from app.services.export.dexpi_exporter import DexpiExporter

router = APIRouter(prefix="", tags=["exports"])


@router.get("/drawings/{drawing_id}/exports/json")
def export_structured_json(drawing_id: int, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Export drawing topology as structured JSON (Section 5.1 of mockup)."""
    repo = DrawingRepository(db)
    drawing = repo.get_drawing_with_details(drawing_id)
    if not drawing:
        raise HTTPException(status_code=404, detail="Drawing not found")

    return DexpiExporter.to_structured_json(drawing)


@router.get("/drawings/{drawing_id}/exports/dexpi")
def export_dexpi_xml(drawing_id: int, db: Session = Depends(get_db)) -> Response:
    """Export drawing topology as DEXPI-compatible XML (Section 5.2 of mockup)."""
    repo = DrawingRepository(db)
    drawing = repo.get_drawing_with_details(drawing_id)
    if not drawing:
        raise HTTPException(status_code=404, detail="Drawing not found")

    xml_content = DexpiExporter.to_dexpi_xml(drawing)
    return Response(
        content=xml_content,
        media_type="application/xml",
        headers={
            "Content-Disposition": f"attachment; filename=dexpi_{drawing.name}.xml"
        },
    )
