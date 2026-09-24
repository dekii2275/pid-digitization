"""Repository for database CRUD operations on P&ID drawings and graph data."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import or_

from app.db.models import (
    Project,
    Drawing,
    DrawingPage,
    ProcessingJob,
    DetectedSymbol,
    OcrText,
    DetectedLine,
    Relationship,
    Revision,
    AuditLog,
    Export,
)


class DrawingRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # Projects
    def create_project(self, name: str, description: Optional[str] = None) -> Project:
        project = Project(name=name, description=description)
        self.db.add(project)
        self.db.commit()
        self.db.refresh(project)
        return project

    def list_projects(self) -> List[Project]:
        return self.db.query(Project).order_by(Project.created_at.desc()).all()

    # Drawings
    def create_drawing(
        self,
        name: str,
        original_filename: str,
        file_path: str,
        file_type: str = "image",
        project_id: Optional[int] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        page_count: int = 1,
    ) -> Drawing:
        drawing = Drawing(
            name=name,
            original_filename=original_filename,
            file_path=file_path,
            file_type=file_type,
            project_id=project_id,
            width=width,
            height=height,
            page_count=page_count,
            status="UPLOADED",
        )
        self.db.add(drawing)
        self.db.commit()
        self.db.refresh(drawing)
        return drawing

    def get_drawing(self, drawing_id: int) -> Optional[Drawing]:
        return self.db.query(Drawing).filter(Drawing.id == drawing_id).first()

    def get_drawing_with_details(self, drawing_id: int) -> Optional[Drawing]:
        return (
            self.db.query(Drawing)
            .options(
                selectinload(Drawing.symbols),
                selectinload(Drawing.ocr_texts),
                selectinload(Drawing.lines),
                selectinload(Drawing.relationships),
            )
            .filter(Drawing.id == drawing_id)
            .first()
        )

    def list_drawings(self, project_id: Optional[int] = None) -> List[Drawing]:
        query = self.db.query(Drawing)
        if project_id is not None:
            query = query.filter(Drawing.project_id == project_id)
        return query.order_by(Drawing.created_at.desc()).all()

    def update_drawing_status(
        self, drawing_id: int, status: str, width: Optional[int] = None, height: Optional[int] = None
    ) -> Optional[Drawing]:
        drawing = self.get_drawing(drawing_id)
        if drawing:
            drawing.status = status
            if width is not None:
                drawing.width = width
            if height is not None:
                drawing.height = height
            self.db.commit()
            self.db.refresh(drawing)
        return drawing

    # Processing Jobs
    def create_job(self, job_id: str, drawing_id: int) -> ProcessingJob:
        job = ProcessingJob(
            job_id=job_id,
            drawing_id=drawing_id,
            status="QUEUED",
            current_stage="QUEUED",
            progress=0,
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def get_job(self, job_id: str) -> Optional[ProcessingJob]:
        return self.db.query(ProcessingJob).filter(ProcessingJob.job_id == job_id).first()

    def update_job_progress(
        self,
        job_id: str,
        stage: str,
        progress: int,
        status: str = "RUNNING",
        metadata: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ) -> Optional[ProcessingJob]:
        job = self.get_job(job_id)
        if job:
            job.status = status
            job.current_stage = stage
            job.progress = progress
            if metadata is not None:
                job.stage_metadata = metadata
            if error_message is not None:
                job.error_message = error_message
            self.db.commit()
            self.db.refresh(job)
        return job

    # Bulk Insert AI Results
    def bulk_save_symbols(self, symbols_data: List[Dict[str, Any]]) -> List[DetectedSymbol]:
        objects = [DetectedSymbol(**data) for data in symbols_data]
        self.db.bulk_save_objects(objects, return_defaults=True)
        self.db.commit()
        return objects

    def bulk_save_ocr(self, ocr_data: List[Dict[str, Any]]) -> List[OcrText]:
        objects = [OcrText(**data) for data in ocr_data]
        self.db.bulk_save_objects(objects, return_defaults=True)
        self.db.commit()
        return objects

    def bulk_save_lines(self, lines_data: List[Dict[str, Any]]) -> List[DetectedLine]:
        objects = [DetectedLine(**data) for data in lines_data]
        self.db.bulk_save_objects(objects, return_defaults=True)
        self.db.commit()
        return objects

    def bulk_save_relationships(self, rels_data: List[Dict[str, Any]]) -> List[Relationship]:
        objects = [Relationship(**data) for data in rels_data]
        self.db.bulk_save_objects(objects, return_defaults=True)
        self.db.commit()
        return objects

    def delete_ai_results(self, drawing_id: int) -> None:
        """Remove only prior generated results so reprocessing never duplicates boxes.

        User-reviewed edits are deliberately retained.
        """
        self.db.query(Relationship).filter(
            Relationship.drawing_id == drawing_id, Relationship.source == "AI"
        ).delete(synchronize_session=False)
        self.db.query(OcrText).filter(
            OcrText.drawing_id == drawing_id, OcrText.source == "AI"
        ).delete(synchronize_session=False)
        self.db.query(DetectedLine).filter(
            DetectedLine.drawing_id == drawing_id, DetectedLine.source == "AI"
        ).delete(synchronize_session=False)
        self.db.query(DetectedSymbol).filter(
            DetectedSymbol.drawing_id == drawing_id, DetectedSymbol.source == "AI"
        ).delete(synchronize_session=False)
        self.db.commit()

    # Revisions & Audit
    def record_revision(
        self,
        drawing_id: int,
        entity_type: str,
        entity_id: int,
        action: str,
        before_state: Optional[Dict[str, Any]],
        after_state: Optional[Dict[str, Any]],
        user_identifier: str = "engineer",
    ) -> Revision:
        revision = Revision(
            drawing_id=drawing_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            before_state=before_state,
            after_state=after_state,
            user_identifier=user_identifier,
        )
        self.db.add(revision)
        self.db.commit()
        self.db.refresh(revision)
        return revision

    # Tag Search / Query
    def search_by_tag(self, drawing_id: int, tag: str) -> Dict[str, Any]:
        """Search symbol by tag and find its connected equipment, valves, and instrumentation."""
        target_symbol = (
            self.db.query(DetectedSymbol)
            .filter(
                DetectedSymbol.drawing_id == drawing_id,
                DetectedSymbol.tag.ilike(f"%{tag}%"),
            )
            .first()
        )

        if not target_symbol:
            return {"found": False, "tag": tag, "symbol": None, "connections": []}

        # Find relationships where target_symbol is either source or target
        rels = (
            self.db.query(Relationship)
            .filter(
                Relationship.drawing_id == drawing_id,
                or_(
                    Relationship.from_symbol_id == target_symbol.id,
                    Relationship.to_symbol_id == target_symbol.id,
                ),
            )
            .all()
        )

        connected_items = []
        for r in rels:
            is_from = r.from_symbol_id == target_symbol.id
            other_id = r.to_symbol_id if is_from else r.from_symbol_id
            other_symbol = self.db.query(DetectedSymbol).filter(DetectedSymbol.id == other_id).first()
            if other_symbol:
                connected_items.append(
                    {
                        "relation": r.relation_type,
                        "direction": "outbound" if is_from else "inbound",
                        "connected_symbol_id": other_symbol.id,
                        "connected_symbol_tag": other_symbol.tag,
                        "connected_symbol_category": other_symbol.category,
                        "connected_symbol_class": other_symbol.class_name,
                        "line_tag": r.line_tag,
                    }
                )

        return {
            "found": True,
            "tag": target_symbol.tag,
            "symbol": {
                "id": target_symbol.id,
                "category": target_symbol.category,
                "class_name": target_symbol.class_name,
                "bbox": [target_symbol.bbox_x1, target_symbol.bbox_y1, target_symbol.bbox_x2, target_symbol.bbox_y2],
            },
            "connections": connected_items,
        }
