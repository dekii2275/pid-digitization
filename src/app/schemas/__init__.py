"""Pydantic schemas package for API request and response validation."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# Project Schemas
class ProjectBase(BaseModel):
    name: str = Field(..., max_length=255)
    description: Optional[str] = None


class ProjectCreate(ProjectBase):
    pass


class ProjectResponse(ProjectBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
        from_attributes = True


# Drawing Schemas
class DrawingBase(BaseModel):
    name: str
    original_filename: str
    file_type: str = "image"
    width: Optional[int] = None
    height: Optional[int] = None
    page_count: int = 1


class DrawingCreate(DrawingBase):
    project_id: Optional[int] = None


class DrawingResponse(DrawingBase):
    id: int
    project_id: Optional[int] = None
    file_path: str
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
        from_attributes = True


# Symbol Schemas
class SymbolBase(BaseModel):
    class_name: str
    category: str = "Other"  # Equipment, Pump, Valve, Instrument, Line, Other
    bbox_x1: float
    bbox_y1: float
    bbox_x2: float
    bbox_y2: float
    confidence: float = 1.0
    tag: Optional[str] = None
    source: str = "AI"


class SymbolCreate(SymbolBase):
    drawing_id: int
    page_id: Optional[int] = None


class SymbolUpdate(BaseModel):
    class_name: Optional[str] = None
    category: Optional[str] = None
    bbox_x1: Optional[float] = None
    bbox_y1: Optional[float] = None
    bbox_x2: Optional[float] = None
    bbox_y2: Optional[float] = None
    tag: Optional[str] = None


class SymbolResponse(SymbolBase):
    id: int
    drawing_id: int
    page_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
        from_attributes = True


# OCR Schemas
class OcrBase(BaseModel):
    text: str
    bbox_x1: float
    bbox_y1: float
    bbox_x2: float
    bbox_y2: float
    confidence: float = 1.0
    ocr_engine: str = "PaddleOCR"
    associated_symbol_id: Optional[int] = None
    source: str = "AI"


class OcrUpdate(BaseModel):
    text: Optional[str] = None
    associated_symbol_id: Optional[int] = None


class OcrResponse(OcrBase):
    id: int
    drawing_id: int
    page_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
        from_attributes = True


# Line Schemas
class LineBase(BaseModel):
    line_type: str = "pipe"  # pipe, signal, other
    geometry: Dict[str, Any]  # {"points": [[x1, y1], [x2, y2], ...]}
    confidence: float = 1.0
    flow_direction: Optional[str] = None
    source: str = "AI"


class LineUpdate(BaseModel):
    line_type: Optional[str] = None
    geometry: Optional[Dict[str, Any]] = None
    flow_direction: Optional[str] = None


class LineResponse(LineBase):
    id: int
    drawing_id: int
    page_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
        from_attributes = True


# Relationship Schemas
class RelationshipBase(BaseModel):
    from_symbol_id: int
    to_symbol_id: int
    relation_type: str = "connected_to"  # connected_to, measures, flows_to
    line_id: Optional[int] = None
    line_tag: Optional[str] = None
    confidence: float = 1.0
    source: str = "AI"


class RelationshipResponse(RelationshipBase):
    id: int
    drawing_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
        from_attributes = True


# Job Schemas
class JobCreateResponse(BaseModel):
    job_id: str
    drawing_id: int
    status: str
    message: str


class JobStatusResponse(BaseModel):
    job_id: str
    drawing_id: int
    status: str
    current_stage: str
    progress: int
    error_message: Optional[str] = None
    stage_metadata: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
        from_attributes = True


# Topology Graph Schemas (Cytoscape.js format)
class CytoscapeNodeData(BaseModel):
    id: str
    label: str
    category: str
    tag: Optional[str] = None
    confidence: float = 1.0


class CytoscapeNode(BaseModel):
    data: CytoscapeNodeData


class CytoscapeEdgeData(BaseModel):
    id: str
    source: str
    target: str
    label: str
    line_tag: Optional[str] = None


class CytoscapeEdge(BaseModel):
    data: CytoscapeEdgeData


class TopologyGraphResponse(BaseModel):
    drawing_id: int
    nodes: List[CytoscapeNode]
    edges: List[CytoscapeEdge]
    relation_table: List[Dict[str, Any]]
