"""Portable web API regression tests, independent of local model caches and DB."""

from __future__ import annotations

import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from app import web_main as web


class TestDrawingReview(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        for name in ("APP_ROOT", "PREVIEW_ROOT", "TILE_ROOT", "PIPELINE_ARTIFACTS_ROOT"):
            directory = root / name
            directory.mkdir()
            patcher = patch.object(web, name, directory)
            patcher.start()
            self.addCleanup(patcher.stop)
        web.drawings.clear()
        web.jobs.clear()
        patcher = patch.object(web, "init_library")
        self.init_library = patcher.start()
        self.addCleanup(patcher.stop)
        self.client = self.enterContext(TestClient(web.app))

    def upload(self):
        buffer = io.BytesIO()
        Image.new("RGB", (800, 600), "white").save(buffer, "PNG")
        return self.client.post("/api/v1/documents/upload", files={"file": ("drawing.png", buffer.getvalue(), "image/png")})

    def test_startup_health_upload_preview_and_tiles(self):
        self.init_library.assert_called_once()
        self.assertEqual(self.client.get("/health").status_code, 200)
        response = self.upload()
        self.assertEqual(response.status_code, 201)
        drawing = response.json()
        self.assertEqual((drawing["width"], drawing["height"]), (800, 600))
        self.assertEqual(self.client.get(f"/api/v1/documents/{drawing['id']}").json(), drawing)
        preview = self.client.get(drawing["preview_url"])
        self.assertEqual(preview.headers["content-type"], "image/jpeg")
        tile = drawing["tile_url_template"].format(z=drawing["max_zoom"], x=0, y=0)
        self.assertEqual(self.client.get(tile).headers["content-type"], "image/png")
        self.assertEqual(self.client.get(tile.replace("/pages/1/", "/pages/0/")).status_code, 404)
        self.assertEqual(self.client.get(tile.replace("/pages/1/", "/pages/2/")).status_code, 404)
        self.assertEqual(self.client.get(tile.replace("/0/0.png", "/999/0.png")).status_code, 404)

    def test_rejects_unsupported_corrupt_and_oversized_uploads(self):
        self.assertEqual(self.client.post("/api/v1/documents/upload", files={"file": ("bad.exe", b"bad")}).status_code, 415)
        self.assertEqual(self.client.post("/api/v1/documents/upload", files={"file": ("bad.png", b"bad")}).status_code, 422)
        with patch.object(web, "MAX_UPLOAD_BYTES", 1):
            self.assertEqual(self.upload().status_code, 413)
        self.assertEqual(list(web.APP_ROOT.iterdir()), [])

    def test_pdf_upload_and_invalid_page(self):
        buffer = io.BytesIO()
        Image.new("RGB", (200, 200), "white").save(buffer, "PDF")
        response = self.client.post("/api/v1/documents/upload", files={"file": ("drawing.pdf", buffer.getvalue(), "application/pdf")})
        self.assertEqual(response.status_code, 201)
        drawing = response.json()
        self.assertEqual(drawing["page_count"], 1)
        self.assertEqual(self.client.get(drawing["preview_url"]).status_code, 200)
        self.assertEqual(self.client.get(drawing["preview_url"].replace("/pages/1/", "/pages/0/")).status_code, 404)

    def test_pipeline_uses_repository_paths_and_reports_missing_weights(self):
        drawing_id = self.upload().json()["id"]
        drawing = web.drawings[drawing_id]
        job = web.PipelineJob("test-job", drawing_id)
        with patch.object(web, "PIPELINE_WEIGHTS", Path(self.temp.name) / "missing.pt"):
            web.run_pipeline_job(job, drawing)
        self.assertEqual(job.status, "FAILED")
        self.assertIn("missing.pt", job.error_message)
        weights = Path(self.temp.name) / "best.pt"
        weights.touch()
        result = web.PIPELINE_ARTIFACTS_ROOT / drawing_id / job.job_id / "editor/scene.json"
        result.parent.mkdir(parents=True)
        result.write_text('{"objects": []}', encoding="utf-8")
        process = Mock(stdout=iter(["tiled_inference.py\n"]), returncode=0)
        process.wait.return_value = 0
        with patch.object(web, "PIPELINE_WEIGHTS", weights), patch.object(web.subprocess, "Popen", return_value=process) as popen:
            web.run_pipeline_job(job, drawing)
        self.assertEqual(job.status, "COMPLETED")
        self.assertEqual(job.result_path, result)
        self.assertEqual(popen.call_args.kwargs["cwd"], web.REPO_ROOT)
        self.assertEqual(popen.call_args.kwargs["env"]["PYTHONPATH"], str(web.REPO_ROOT / "src"))
        self.assertEqual(Path(popen.call_args.args[0][1]), web.REPO_ROOT / "training/yolov8s/run_pid_pipeline.py")
