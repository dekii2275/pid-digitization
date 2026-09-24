"""Integration tests for FastAPI REST API v1 and Worker Pipeline (Milestone M2)."""

from __future__ import annotations

import io
import sys
from pathlib import Path
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from app.core.database import Base, get_db
from app.main import app
from app.services.pipeline.yolo_detector import YoloDetection
from app.workers.pipeline_worker import worker_instance


class TestApiV1(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # In-memory SQLite with StaticPool so all sessions share the same tables
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            echo=False,
        )
        Base.metadata.create_all(cls.engine)
        cls.TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=cls.engine)

        def override_get_db():
            db = cls.TestingSessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()

    def test_01_health_check(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "healthy")

    def test_02_projects_api(self):
        # Create project
        resp = self.client.post("/api/v1/projects", json={"name": "Refinery Unit 100", "description": "Main P&ID"})
        self.assertEqual(resp.status_code, 200)
        project = resp.json()
        self.assertEqual(project["name"], "Refinery Unit 100")
        self.assertIn("id", project)

        # List projects
        list_resp = self.client.get("/api/v1/projects")
        self.assertEqual(list_resp.status_code, 200)
        self.assertGreaterEqual(len(list_resp.json()), 1)

    def test_03_upload_drawing(self):
        # Create a test image in memory
        img = Image.new("RGB", (1000, 800), color="white")
        img_bytes = io.BytesIO()
        img.save(img_bytes, format="JPEG")
        img_bytes.seek(0)

        response = self.client.post(
            "/api/v1/drawings/upload",
            files={"file": ("test_pid.jpg", img_bytes, "image/jpeg")},
            data={"name": "PID-101", "project_id": 1},
        )
        self.assertEqual(response.status_code, 200)
        drawing = response.json()
        self.assertEqual(drawing["name"], "PID-101")
        self.assertEqual(drawing["file_type"], "image")
        self.assertEqual(drawing["width"], 1000)
        self.assertEqual(drawing["height"], 800)
        self.assertEqual(drawing["status"], "UPLOADED")

    def test_04_process_job_saves_real_detector_contract(self):
        img = Image.new("RGB", (7168, 4561), color="white")
        img_bytes = io.BytesIO()
        img.save(img_bytes, format="JPEG")
        img_bytes.seek(0)

        upload_resp = self.client.post(
            "/api/v1/drawings/upload",
            files={"file": ("pipeline_input.jpg", img_bytes, "image/jpeg")},
            data={"name": "Pipeline input", "project_id": 1},
        )
        drawing = upload_resp.json()
        drawing_id = drawing["id"]

        # 1. Submit process job
        process_resp = self.client.post(f"/api/v1/drawings/{drawing_id}/process")
        self.assertEqual(process_resp.status_code, 200)
        job_info = process_resp.json()
        job_id = job_info["job_id"]
        self.assertEqual(job_info["status"], "QUEUED")

        # 2. Check initial job status
        status_resp = self.client.get(f"/api/v1/jobs/{job_id}")
        self.assertEqual(status_resp.status_code, 200)
        self.assertEqual(status_resp.json()["status"], "QUEUED")

        # 3. Simulate the trained detector contract. The test intentionally does
        # not import a checkpoint or any checked-in artifact.
        worker_instance.service.session_factory = self.TestingSessionLocal
        original_detect_image = worker_instance.service.symbol_detector.detect_image
        worker_instance.service.symbol_detector.detect_image = lambda _path: [
            YoloDetection(
                class_id=11,
                class_name="Gate valve NC",
                confidence=0.91,
                bbox=(100.0, 120.0, 180.0, 210.0),
            )
        ]
        try:
            worker_instance.process_job(job_id=job_id, drawing_id=drawing_id)
        finally:
            worker_instance.service.symbol_detector.detect_image = original_detect_image

        # 4. Only predictions returned by the detector may be persisted.
        completed_resp = self.client.get(f"/api/v1/jobs/{job_id}")
        self.assertEqual(completed_resp.status_code, 200)
        completed_job = completed_resp.json()
        self.assertEqual(completed_job["status"], "COMPLETED")
        self.assertEqual(completed_job["progress"], 100)
        self.assertEqual(completed_job["stage_metadata"]["detected_symbols"], 1)

        # 5. Check symbols API
        symbols_resp = self.client.get(f"/api/v1/drawings/{drawing_id}/symbols")
        self.assertEqual(symbols_resp.status_code, 200)
        symbols = symbols_resp.json()
        self.assertEqual(len(symbols), 1)
        self.assertEqual(symbols[0]["class_name"], "Gate valve NC")
        self.assertEqual(symbols[0]["category"], "Valve")
        self.assertEqual(symbols[0]["source"], "AI")

        # 6. Check OCR API
        ocr_resp = self.client.get(f"/api/v1/drawings/{drawing_id}/ocr")
        self.assertEqual(ocr_resp.status_code, 200)
        self.assertEqual(ocr_resp.json(), [])

        # 7. Check Lines API
        lines_resp = self.client.get(f"/api/v1/drawings/{drawing_id}/lines")
        self.assertEqual(lines_resp.status_code, 200)
        self.assertEqual(lines_resp.json(), [])

        # 8. Check Topology API (Cytoscape format & relation table)
        topo_resp = self.client.get(f"/api/v1/drawings/{drawing_id}/topology")
        self.assertEqual(topo_resp.status_code, 200)
        topo_data = topo_resp.json()
        self.assertIn("nodes", topo_data)
        self.assertIn("edges", topo_data)
        self.assertIn("relation_table", topo_data)
        self.assertEqual(len(topo_data["nodes"]), 1)
        self.assertEqual(topo_data["nodes"][0]["data"]["label"], "Valve:1")
        self.assertEqual(topo_data["edges"], [])
        self.assertEqual(topo_data["relation_table"], [])

    def test_05_human_in_the_loop_symbol_editing(self):
        # Add manual symbol
        create_resp = self.client.post(
            "/api/v1/symbols",
            json={
                "drawing_id": 1,
                "class_name": "Gate valve NC",
                "category": "Valve",
                "bbox_x1": 50.0,
                "bbox_y1": 60.0,
                "bbox_x2": 120.0,
                "bbox_y2": 130.0,
                "confidence": 1.0,
                "tag": "V-1001",
                "source": "USER",
            },
        )
        self.assertEqual(create_resp.status_code, 200)
        symbol = create_resp.json()
        symbol_id = symbol["id"]
        self.assertEqual(symbol["tag"], "V-1001")

        # Update symbol (change tag to V-1002)
        update_resp = self.client.put(f"/api/v1/symbols/{symbol_id}", json={"tag": "V-1002"})
        self.assertEqual(update_resp.status_code, 200)
        self.assertEqual(update_resp.json()["tag"], "V-1002")

        # Delete symbol
        del_resp = self.client.delete(f"/api/v1/symbols/{symbol_id}")
        self.assertEqual(del_resp.status_code, 200)


if __name__ == "__main__":
    unittest.main(verbosity=2)
