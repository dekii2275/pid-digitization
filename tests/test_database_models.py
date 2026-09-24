"""Unit & integration tests for SQLAlchemy database models and DrawingRepository (Milestone M1)."""

from __future__ import annotations

import sys
from pathlib import Path
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from app.core.database import Base
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
from app.db.repositories.drawing_repository import DrawingRepository


class TestDatabaseModels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # In-memory SQLite for testing schema and repository operations
        cls.engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(cls.engine)
        cls.Session = sessionmaker(bind=cls.engine)

    def setUp(self):
        self.session = self.Session()
        self.repo = DrawingRepository(self.session)

    def tearDown(self):
        self.session.rollback()
        self.session.close()

    def test_01_create_project_and_drawing(self):
        project = self.repo.create_project(name="Project Alpha", description="Refinery Unit 100")
        self.assertIsNotNone(project.id)
        self.assertEqual(project.name, "Project Alpha")

        drawing = self.repo.create_drawing(
            name="PID-001",
            original_filename="pid_unit100.pdf",
            file_path="/uploads/pid_unit100.pdf",
            file_type="pdf",
            project_id=project.id,
            width=7168,
            height=4561,
            page_count=1,
        )
        self.assertIsNotNone(drawing.id)
        self.assertEqual(drawing.project_id, project.id)
        self.assertEqual(drawing.status, "UPLOADED")

    def test_02_processing_job_lifecycle(self):
        project = self.repo.create_project(name="Job Test Project")
        drawing = self.repo.create_drawing(
            name="PID-Job", original_filename="test.jpg", file_path="/uploads/test.jpg", project_id=project.id
        )

        job = self.repo.create_job(job_id="job-12345", drawing_id=drawing.id)
        self.assertEqual(job.status, "QUEUED")
        self.assertEqual(job.progress, 0)

        # Update progress through stages
        updated = self.repo.update_job_progress(
            job_id="job-12345",
            stage="RUNNING_OCR",
            progress=45,
            metadata={"ocr_engine": "PP-OCRv5", "tiles_processed": 15},
        )
        self.assertEqual(updated.current_stage, "RUNNING_OCR")
        self.assertEqual(updated.progress, 45)
        self.assertEqual(updated.stage_metadata["tiles_processed"], 15)

    def test_03_bulk_save_ai_results_and_topology(self):
        project = self.repo.create_project(name="Topology Test Project")
        drawing = self.repo.create_drawing(
            name="PID-Topology", original_filename="4.jpg", file_path="/uploads/4.jpg", project_id=project.id
        )

        # 1. Symbols
        symbols_data = [
            {
                "drawing_id": drawing.id,
                "class_name": "Storage tank",
                "category": "Equipment",
                "bbox_x1": 100.0,
                "bbox_y1": 200.0,
                "bbox_x2": 400.0,
                "bbox_y2": 600.0,
                "confidence": 0.98,
                "tag": "T-101",
                "source": "AI",
            },
            {
                "drawing_id": drawing.id,
                "class_name": "Centrifugal pump",
                "category": "Pump",
                "bbox_x1": 500.0,
                "bbox_y1": 500.0,
                "bbox_x2": 650.0,
                "bbox_y2": 650.0,
                "confidence": 0.95,
                "tag": "P-101",
                "source": "AI",
            },
            {
                "drawing_id": drawing.id,
                "class_name": "Pressure Indicator",
                "category": "Instrument",
                "bbox_x1": 200.0,
                "bbox_y1": 100.0,
                "bbox_x2": 260.0,
                "bbox_y2": 160.0,
                "confidence": 0.96,
                "tag": "PI-101",
                "source": "AI",
            },
        ]
        symbols = self.repo.bulk_save_symbols(symbols_data)
        self.assertEqual(len(symbols), 3)
        t101_id = symbols[0].id
        p101_id = symbols[1].id
        pi101_id = symbols[2].id

        # 2. OCR texts
        ocr_data = [
            {
                "drawing_id": drawing.id,
                "text": "T-101",
                "bbox_x1": 220.0,
                "bbox_y1": 380.0,
                "bbox_x2": 280.0,
                "bbox_y2": 400.0,
                "confidence": 0.99,
                "associated_symbol_id": t101_id,
            },
            {
                "drawing_id": drawing.id,
                "text": "P-101",
                "bbox_x1": 550.0,
                "bbox_y1": 660.0,
                "bbox_x2": 600.0,
                "bbox_y2": 680.0,
                "confidence": 0.97,
                "associated_symbol_id": p101_id,
            },
        ]
        ocr_texts = self.repo.bulk_save_ocr(ocr_data)
        self.assertEqual(len(ocr_texts), 2)

        # 3. Lines with Polyline JSON geometry
        lines_data = [
            {
                "drawing_id": drawing.id,
                "line_type": "pipe",
                "geometry": {"points": [[400.0, 550.0], [450.0, 550.0], [450.0, 580.0], [500.0, 580.0]]},
                "confidence": 0.92,
                "flow_direction": "left-to-right",
            }
        ]
        lines = self.repo.bulk_save_lines(lines_data)
        self.assertEqual(len(lines), 1)
        line_id = lines[0].id

        # 4. Relationships (Graph edges)
        rels_data = [
            {
                "drawing_id": drawing.id,
                "from_symbol_id": t101_id,
                "to_symbol_id": p101_id,
                "relation_type": "connected_to",
                "line_id": line_id,
                "line_tag": '6"-P-1001',
                "confidence": 0.94,
            },
            {
                "drawing_id": drawing.id,
                "from_symbol_id": pi101_id,
                "to_symbol_id": t101_id,
                "relation_type": "measures",
                "line_id": None,
                "line_tag": None,
                "confidence": 0.96,
            },
        ]
        rels = self.repo.bulk_save_relationships(rels_data)
        self.assertEqual(len(rels), 2)

        # 5. Test Tag Search for "T-101"
        query_result = self.repo.search_by_tag(drawing_id=drawing.id, tag="T-101")
        self.assertTrue(query_result["found"])
        self.assertEqual(query_result["tag"], "T-101")
        self.assertEqual(len(query_result["connections"]), 2)

        connections = query_result["connections"]
        connected_tags = {c["connected_symbol_tag"] for c in connections}
        self.assertIn("P-101", connected_tags)
        self.assertIn("PI-101", connected_tags)

    def test_04_revision_and_audit_logging(self):
        project = self.repo.create_project(name="Revision Test Project")
        drawing = self.repo.create_drawing(
            name="PID-Rev", original_filename="rev.jpg", file_path="/uploads/rev.jpg", project_id=project.id
        )

        # Record revision: engineer edits connection from V-103 to V-102
        revision = self.repo.record_revision(
            drawing_id=drawing.id,
            entity_type="relationship",
            entity_id=42,
            action="UPDATE",
            before_state={"from": "P-101", "to": "V-103", "relation": "connected_to"},
            after_state={"from": "P-101", "to": "V-102", "relation": "connected_to"},
            user_identifier="engineer_vpi",
        )
        self.assertIsNotNone(revision.id)
        self.assertEqual(revision.action, "UPDATE")
        self.assertEqual(revision.after_state["to"], "V-102")


if __name__ == "__main__":
    unittest.main(verbosity=2)
