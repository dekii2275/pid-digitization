"""API routes for topology reconstruction and Cytoscape.js graph representation."""

from __future__ import annotations

from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.db.models import Drawing, DetectedSymbol, Relationship
from app.db.repositories.drawing_repository import DrawingRepository
from app.schemas import (
    CytoscapeEdge,
    CytoscapeEdgeData,
    CytoscapeNode,
    CytoscapeNodeData,
    RelationshipBase,
    RelationshipResponse,
    TopologyGraphResponse,
)

router = APIRouter(prefix="", tags=["topology"])


@router.get("/drawings/{drawing_id}/topology", response_model=TopologyGraphResponse)
def get_drawing_topology(drawing_id: int, db: Session = Depends(get_db)):
    """Return topological graph data in Cytoscape.js format and relationship extraction table."""
    symbols = db.query(DetectedSymbol).filter(DetectedSymbol.drawing_id == drawing_id).all()
    relationships = db.query(Relationship).filter(Relationship.drawing_id == drawing_id).all()

    symbol_map = {s.id: s for s in symbols}

    nodes: List[CytoscapeNode] = []
    for s in symbols:
        label = s.tag or f"{s.category}:{s.id}"
        nodes.append(
            CytoscapeNode(
                data=CytoscapeNodeData(
                    id=str(s.id),
                    label=label,
                    category=s.category or "Other",
                    tag=s.tag,
                    confidence=s.confidence,
                )
            )
        )

    edges: List[CytoscapeEdge] = []
    relation_table: List[Dict[str, Any]] = []

    for r in relationships:
        from_sym = symbol_map.get(r.from_symbol_id)
        to_sym = symbol_map.get(r.to_symbol_id)
        edge_label = r.relation_type
        if r.line_tag:
            edge_label += f" ({r.line_tag})"

        edges.append(
            CytoscapeEdge(
                data=CytoscapeEdgeData(
                    id=str(r.id),
                    source=str(r.from_symbol_id),
                    target=str(r.to_symbol_id),
                    label=edge_label,
                    line_tag=r.line_tag,
                )
            )
        )

        relation_table.append(
            {
                "id": r.id,
                "from": from_sym.tag if from_sym and from_sym.tag else f"sym_{r.from_symbol_id}",
                "relation": r.relation_type,
                "to": to_sym.tag if to_sym and to_sym.tag else f"sym_{r.to_symbol_id}",
                "line": r.line_tag or (f"line_{r.line_id}" if r.line_id else "-"),
                "confidence": r.confidence,
            }
        )

    return TopologyGraphResponse(
        drawing_id=drawing_id,
        nodes=nodes,
        edges=edges,
        relation_table=relation_table,
    )


@router.post("/drawings/{drawing_id}/relationships", response_model=RelationshipResponse)
def create_relationship(drawing_id: int, payload: RelationshipBase, db: Session = Depends(get_db)):
    """Manually add a relationship between two symbols and record revision."""
    repo = DrawingRepository(db)
    rel = Relationship(
        drawing_id=drawing_id,
        from_symbol_id=payload.from_symbol_id,
        to_symbol_id=payload.to_symbol_id,
        relation_type=payload.relation_type,
        line_id=payload.line_id,
        line_tag=payload.line_tag,
        confidence=payload.confidence,
        source="USER",
    )
    db.add(rel)
    db.commit()
    db.refresh(rel)

    repo.record_revision(
        drawing_id=drawing_id,
        entity_type="relationship",
        entity_id=rel.id,
        action="CREATE",
        before_state=None,
        after_state={
            "from_symbol_id": rel.from_symbol_id,
            "to_symbol_id": rel.to_symbol_id,
            "relation_type": rel.relation_type,
            "line_tag": rel.line_tag,
        },
    )
    return rel


@router.delete("/relationships/{rel_id}")
def delete_relationship(rel_id: int, db: Session = Depends(get_db)):
    """Delete a relationship and record revision."""
    repo = DrawingRepository(db)
    rel = db.query(Relationship).filter(Relationship.id == rel_id).first()
    if not rel:
        raise HTTPException(status_code=404, detail="Relationship not found")

    drawing_id = rel.drawing_id
    before_state = {
        "from_symbol_id": rel.from_symbol_id,
        "to_symbol_id": rel.to_symbol_id,
        "relation_type": rel.relation_type,
        "line_tag": rel.line_tag,
    }

    db.delete(rel)
    db.commit()

    repo.record_revision(
        drawing_id=drawing_id,
        entity_type="relationship",
        entity_id=rel_id,
        action="DELETE",
        before_state=before_state,
        after_state=None,
    )
    return {"message": "Relationship deleted successfully"}
