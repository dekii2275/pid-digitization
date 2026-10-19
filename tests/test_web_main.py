"""Portable web API regression tests, independent of local model caches and DB."""

from __future__ import annotations

import copy
import hashlib
import io
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import pypdfium2 as pdfium
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from app import web_main as web


class MemoryDocumentStorage:
    """External storage stand-in; survives clearing the API's process cache."""

    def __init__(self):
        self.documents = {}
        self.objects = {}
        self.annotations = {}
        self.classes = []

    def get_document(self, drawing_id):
        metadata = self.documents.get(drawing_id)
        if metadata is None:
            return None
        result = copy.deepcopy(metadata)
        pages = [
            (page, data) for (id_, page), data in self.annotations.items() if id_ == drawing_id
        ]
        result["annotation_count"] = sum(
            len(data["symbols"]) + len(data["texts"]) for _, data in pages
        )
        result["labeled_pages"] = sorted(
            page for page, data in pages if data["symbols"] or data["texts"]
        )
        result["last_labeled_at"] = max((data["saved_at"] for _, data in pages), default=None)
        result["page_workflows"] = web.document_storage.page_workflows(
            metadata,
            {
                str(page): dict(
                    annotation_revision=data["revision"],
                    annotation_count=len(data["symbols"]) + len(data["texts"]),
                )
                for page, data in pages
            },
        )
        result["completed_page_count"] = sum(
            item["status"] == "completed" for item in result["page_workflows"].values()
        )
        result["updated_at"] = max(
            metadata.get("updated_at", metadata["created_at"]), result["last_labeled_at"] or ""
        )
        return result

    def list_documents(self, labeled=None):
        documents = [self.get_document(key) for key in self.documents]
        return sorted(
            [
                item
                for item in documents
                if labeled is None or (item["annotation_count"] > 0) == labeled
            ],
            key=lambda item: item["created_at"],
            reverse=True,
        )

    def save_source(self, drawing_id, source, metadata):
        data = source.read_bytes()
        self.objects[drawing_id] = data
        self.documents[drawing_id] = dict(
            metadata,
            drawing_id=drawing_id,
            bucket="test-drawings",
            object_key=f"drawings/{drawing_id}/original{metadata['extension']}",
            byte_size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
        )
        return self.get_document(drawing_id)

    def cache_source(self, document, destination):
        if not destination.exists():
            destination.write_bytes(self.objects[document["drawing_id"]])
        return destination

    def delete_document(self, drawing_id):
        self.documents.pop(drawing_id)
        self.objects.pop(drawing_id)
        self.annotations = {
            key: value for key, value in self.annotations.items() if key[0] != drawing_id
        }

    def read_annotation(self, drawing_id, page):
        return copy.deepcopy(self.annotations.get((drawing_id, page)))

    def save_annotation(self, drawing_id, page, data, expected_revision):
        existing = self.annotations.get((drawing_id, page))
        if (existing["revision"] if existing else 0) != expected_revision:
            raise HTTPException(409, "Annotation conflict")
        self.annotations[drawing_id, page] = copy.deepcopy(data)
        metadata = self.documents[drawing_id]
        workflows = metadata.setdefault("page_workflows", {})
        previous = workflows.get(str(page), {})
        previous_content = existing or dict(symbols=[], texts=[], relations=[])
        if (
            any(
                previous_content.get(key) != data.get(key)
                for key in ("symbols", "texts", "relations")
            )
            or previous.get("status", "not_started") == "not_started"
        ):
            workflows[str(page)] = dict(
                status="in_progress",
                revision=previous.get("revision", 0) + 1,
                updated_at=data["saved_at"],
            )
        metadata["updated_at"] = data["saved_at"]

    def update_document(self, drawing_id, changes):
        self.documents[drawing_id].update(
            copy.deepcopy(changes), updated_at=datetime.now(timezone.utc).isoformat()
        )

    def save_page_status(self, drawing_id, page, status, expected_revision, annotation_revision):
        metadata = self.documents[drawing_id]
        if not 1 <= page <= metadata["page_count"]:
            raise HTTPException(404, "Invalid page")
        workflow = self.get_document(drawing_id)["page_workflows"].get(str(page), {})
        if (
            workflow.get("revision", 0) != expected_revision
            or workflow.get("annotation_revision", 0) != annotation_revision
        ):
            raise HTTPException(409, "Workflow conflict")
        now = datetime.now(timezone.utc).isoformat()
        metadata.setdefault("page_workflows", {})[str(page)] = dict(
            status=status, revision=expected_revision + 1, updated_at=now
        )
        metadata["updated_at"] = now

    def sync_classes(self, catalog):
        known = {item["code"] for item in self.classes}
        for item in sorted(catalog, key=lambda item: item["code"]):
            if item["enabled"] and item["code"] not in known:
                self.classes.append(
                    dict(
                        id=len(self.classes),
                        code=item["code"],
                        name=item["name"],
                        category=item["category"],
                    )
                )
                known.add(item["code"])
        return copy.deepcopy(self.classes)


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
        self.storage = MemoryDocumentStorage()
        self.enterContext(patch.object(web.asset_catalog, "save_review_scene"))
        self.enterContext(patch.object(web.drawing_editor, "save_processed_scene"))
        for name in (
            "get_document",
            "list_documents",
            "save_source",
            "cache_source",
            "delete_document",
            "read_annotation",
            "save_annotation",
            "sync_classes",
            "update_document",
            "save_page_status",
        ):
            patcher = patch.object(web.document_storage, name, getattr(self.storage, name))
            patcher.start()
            self.addCleanup(patcher.stop)
        for name in ("init_documents", "connection", "client"):
            patcher = patch.object(web.document_storage, name)
            patched = patcher.start()
            self.addCleanup(patcher.stop)
            if name == "connection":
                from unittest.mock import MagicMock

                patched.return_value = MagicMock()
        self.client = self.enterContext(TestClient(web.app))

    def upload(self):
        buffer = io.BytesIO()
        Image.new("RGB", (800, 600), "white").save(buffer, "PNG")
        return self.client.post(
            "/api/v1/documents/upload",
            files={"file": ("drawing.png", buffer.getvalue(), "image/png")},
        )

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
        self.assertEqual(
            self.client.post(
                "/api/v1/documents/upload", files={"file": ("bad.exe", b"bad")}
            ).status_code,
            415,
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/documents/upload", files={"file": ("bad.png", b"bad")}
            ).status_code,
            422,
        )
        with patch.object(web, "MAX_UPLOAD_BYTES", 1):
            self.assertEqual(self.upload().status_code, 413)
        self.assertEqual(list(web.APP_ROOT.iterdir()), [])

    def test_pdf_upload_and_invalid_page(self):
        buffer = io.BytesIO()
        Image.new("RGB", (200, 200), "white").save(buffer, "PDF")
        response = self.client.post(
            "/api/v1/documents/upload",
            files={"file": ("drawing.pdf", buffer.getvalue(), "application/pdf")},
        )
        self.assertEqual(response.status_code, 201)
        drawing = response.json()
        self.assertEqual(drawing["page_count"], 1)
        self.assertEqual(self.client.get(drawing["preview_url"]).status_code, 200)
        self.assertEqual(
            self.client.get(drawing["preview_url"].replace("/pages/1/", "/pages/0/")).status_code,
            404,
        )

    def upload_vector_pdf(self):
        buffer = io.BytesIO()
        pdf = pdfium.PdfDocument.new()
        try:
            pdf.new_page(72, 144).close()
            pdf.new_page(144, 72).close()
            pdf.save(buffer)
        finally:
            pdf.close()
        response = self.client.post(
            "/api/v1/documents/upload",
            files={"file": ("vector.pdf", buffer.getvalue(), "application/pdf")},
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_lightweight_pdf_pages_tiles_and_restart(self):
        drawing = self.upload_vector_pdf()
        self.assertEqual((drawing["width"], drawing["height"]), (144, 288))
        self.assertEqual(drawing["render_dpi"], 144)
        base = f"/api/v1/documents/{drawing['id']}/pages"
        web.drawings.clear()
        with patch.object(web, "PDF_RENDER_DPI", 600):
            page = self.client.get(f"{base}/2").json()
        self.assertEqual((page["width"], page["height"]), (288, 144))
        tile = page["tile_url_template"].format(z=page["max_zoom"], x=0, y=0)
        with Image.open(io.BytesIO(self.client.get(tile).content)) as image:
            self.assertEqual(image.size, (288, 144))
        self.assertEqual(self.client.get(page["preview_url"]).status_code, 200)

    def test_existing_high_resolution_pdf_pages_tiles_and_restart(self):
        with patch.object(web, "PDF_RENDER_DPI", 600):
            drawing = self.upload_vector_pdf()
        self.assertEqual((drawing["width"], drawing["height"]), (600, 1200))
        self.assertEqual(drawing["render_dpi"], 600)
        base = f"/api/v1/documents/{drawing['id']}/pages"
        web.drawings.clear()
        # Stored render settings win even if the default changes after restart.
        with patch.object(web, "PDF_RENDER_DPI", 72):
            page = self.client.get(f"{base}/2").json()
        self.assertEqual((page["width"], page["height"]), (1200, 600))
        record = web.record_or_404(drawing["id"])
        with Image.open(web.page_image(record, 2)) as image:
            self.assertEqual(image.format, "PNG")
            self.assertAlmostEqual(image.info["dpi"][0], 600, delta=0.1)
        tile = page["tile_url_template"].format(z=page["max_zoom"], x=0, y=0)
        with Image.open(io.BytesIO(self.client.get(tile).content)) as image:
            self.assertEqual(image.size, (512, 512))
        # Reuse the lossless render on disk instead of re-rendering every restart.
        web.drawings.clear()
        with patch.object(web.pdfium, "PdfDocument", side_effect=AssertionError("cached")):
            self.assertEqual(self.client.get(f"{base}/2").json(), page)

    def test_large_pdf_is_bounded_and_preserves_aspect_ratio(self):
        with patch.object(web, "PDF_MAX_RENDER_PIXELS", 100_000):
            drawing = self.upload_vector_pdf()
        self.assertLessEqual(drawing["width"] * drawing["height"], 100_000)
        self.assertLess(abs(drawing["height"] - 2 * drawing["width"]), 2)
        web.drawings.clear()
        page = self.client.get(f"/api/v1/documents/{drawing['id']}/pages/2").json()
        self.assertLessEqual(page["width"] * page["height"], 100_000)

    def test_legacy_pdf_retains_annotation_coordinates(self):
        with patch.object(web, "PDF_RENDER_DPI", 144):
            drawing = self.upload_vector_pdf()
        data = self.storage.documents[drawing["id"]]
        del data["render_dpi"], data["render_max_pixels"]
        web.drawings.clear()
        record = web.record_or_404(drawing["id"])
        web.page_image(record, 1).unlink()
        record.rendered_pages.clear()
        page = self.client.get(f"/api/v1/documents/{drawing['id']}/pages/1").json()
        self.assertEqual((page["width"], page["height"]), (144, 288))
        self.assertEqual(page["render_dpi"], 144)

    def test_minio_source_survives_cache_loss_and_delete_removes_all_artifacts(self):
        drawing = self.upload().json()
        self.assertTrue(drawing["file_path"].startswith("s3://test-drawings/"))
        self.assertEqual(list(web.APP_ROOT.glob("*.json")), [])
        web.drawings.clear()
        for path in web.APP_ROOT.iterdir():
            path.unlink()
        self.assertEqual(
            self.client.get(drawing["original_url"]).content, self.storage.objects[drawing["id"]]
        )
        self.assertEqual(self.client.get(drawing["preview_url"]).status_code, 200)
        self.assertEqual(self.client.delete(f"/api/v1/documents/{drawing['id']}").status_code, 200)
        self.assertNotIn(drawing["id"], self.storage.objects)
        self.assertEqual(self.client.get(drawing["original_url"]).status_code, 404)
        self.assertEqual(self.client.get(drawing["preview_url"]).status_code, 404)
        self.assertEqual(self.client.get("/api/v1/documents").json(), [])
        self.assertFalse((web.PREVIEW_ROOT / drawing["id"]).exists())
        self.assertEqual(self.client.delete(f"/api/v1/documents/{drawing['id']}").status_code, 404)

    def test_failed_storage_upload_does_not_leave_files_or_catalog_entries(self):
        from psycopg import OperationalError

        with patch.object(
            web.document_storage, "save_source", side_effect=OperationalError("unavailable")
        ):
            self.assertEqual(self.upload().status_code, 503)
        self.assertEqual(self.client.get("/api/v1/documents").json(), [])
        self.assertEqual(list(web.APP_ROOT.iterdir()), [])
        self.assertEqual(list(web.PREVIEW_ROOT.iterdir()), [])

    def test_cannot_delete_drawing_during_pipeline_or_when_storage_is_unavailable(self):
        from psycopg import OperationalError

        drawing = self.upload().json()
        job = web.PipelineJob("running-job", drawing["id"], status="RUNNING")
        web.jobs[job.job_id] = job
        url = f"/api/v1/documents/{drawing['id']}"
        self.assertEqual(self.client.delete(url).status_code, 409)
        job.status = "COMPLETED"
        with patch.object(
            web.document_storage, "delete_document", side_effect=OperationalError("unavailable")
        ):
            self.assertEqual(self.client.delete(url).status_code, 503)
        self.assertEqual(self.client.get(url).status_code, 200)

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
        with (
            patch.object(web, "PIPELINE_WEIGHTS", weights),
            patch.object(web.subprocess, "Popen", return_value=process) as popen,
        ):
            web.run_pipeline_job(job, drawing)
        self.assertEqual(job.status, "COMPLETED")
        self.assertEqual(job.result_path, result)
        self.assertEqual(popen.call_args.kwargs["cwd"], web.REPO_ROOT)
        self.assertEqual(popen.call_args.kwargs["env"]["PYTHONPATH"], str(web.REPO_ROOT / "src"))
        self.assertEqual(
            Path(popen.call_args.args[0][1]), web.REPO_ROOT / "training/yolov8s/run_pid_pipeline.py"
        )
