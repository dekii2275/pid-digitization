"""Manual annotations: native coordinates, durable storage, class IDs and exports."""

import io
import json
import sys
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import test_web_main as fixtures

from app import annotations


class TestAnnotations(unittest.TestCase):
    upload = fixtures.TestDrawingReview.upload

    def setUp(self):
        fixtures.TestDrawingReview.setUp(self)
        self.catalog = [
            dict(code="Z-002", name="Valve B", category="VALVES", enabled=True),
            dict(code="A-001", name="Valve A", category="VALVES", enabled=True),
        ]
        patcher = patch.object(annotations, "list_symbols", side_effect=lambda: self.catalog)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.document = self.upload().json()
        self.base = f"/api/v1/documents/{self.document['id']}/pages/1/annotations"

    def body(self):
        return dict(
            revision=0,
            symbols=[dict(id="s1", label_id="A-001", x=80, y=60, width=160, height=120)],
            texts=[dict(id="t1", text="P-101", x=300, y=100, width=100, height=30)],
            relations=[dict(id="r1", source="t1", target="s1", type="text_of")],
        )

    def test_saved_annotations_export_and_restart(self):
        self.assertEqual(self.client.get(self.base + "/export").status_code, 409)
        initial = self.client.get(self.base).json()
        self.assertEqual(initial["revision"], 0)
        self.assertEqual([item["code"] for item in initial["classes"]], ["A-001", "Z-002"])
        response = self.client.put(self.base, json=self.body())
        self.assertEqual(response.status_code, 200, response.text)
        saved = response.json()
        self.assertEqual(saved["revision"], 1)
        self.assertEqual(saved["symbols"][0]["class_id"], 0)
        self.assertEqual(self.client.put(self.base, json=self.body()).status_code, 409)
        fixtures.web.drawings.clear()
        self.assertEqual(self.client.get(self.base).json(), saved)
        self.assertEqual(self.client.get("/api/v1/documents").json()[0]["id"], self.document["id"])
        archive = self.client.get(self.base + "/export")
        self.assertEqual(archive.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(archive.content)) as zipped:
            label = next(name for name in zipped.namelist() if name.startswith("labels/"))
            fields = zipped.read(label).decode().split()
            self.assertEqual(fields[0], "0")
            self.assertEqual([float(value) for value in fields[1:]], [0.2, 0.2, 0.2, 0.2])
            image_name = next(name for name in zipped.namelist() if name.startswith("images/"))
            with Image.open(io.BytesIO(zipped.read(image_name))) as image:
                self.assertEqual(image.size, (800, 600))
            annotation_name = next(
                name for name in zipped.namelist() if name.startswith("annotations/")
            )
            exported = json.loads(zipped.read(annotation_name))
            self.assertEqual(exported["texts"][0]["text"], "P-101")
            self.assertEqual(exported["relations"], saved["relations"])

    def test_class_ids_survive_catalog_changes(self):
        saved = self.client.put(self.base, json=self.body()).json()
        self.catalog = [
            dict(code="0-NEW", name="New", category="OTHER", enabled=True),
            dict(code="Z-002", name="Renamed", category="VALVES", enabled=False),
        ]
        reloaded = self.client.get(self.base).json()
        self.assertEqual(reloaded["classes"][:2], saved["classes"])
        self.assertEqual(reloaded["classes"][2]["code"], "0-NEW")
        self.assertEqual(reloaded["classes"][2]["id"], 2)
        another = self.upload().json()
        another_classes = self.client.get(
            f"/api/v1/documents/{another['id']}/pages/1/annotations"
        ).json()["classes"]
        self.assertEqual(another_classes, reloaded["classes"])
        body = self.body()
        body["revision"] = 1
        self.assertEqual(self.client.put(self.base, json=body).status_code, 200)

    def test_invalid_boxes_labels_and_relations_do_not_overwrite(self):
        variants = []
        for change in [dict(x=-1), dict(width=0), dict(x=790, width=20), dict(label_id="UNKNOWN")]:
            body = self.body()
            body["symbols"][0].update(change)
            variants.append(body)
        body = self.body()
        body["texts"][0]["id"] = "s1"
        variants.append(body)
        for change in [
            dict(source="missing"),
            dict(source="s1", target="s1"),
            dict(type="flow_to"),
        ]:
            body = self.body()
            body["relations"][0].update(change)
            variants.append(body)
        for body in variants:
            with self.subTest(body=body):
                self.assertEqual(self.client.put(self.base, json=body).status_code, 422)
        self.assertEqual(self.client.get(self.base).json()["revision"], 0)
        self.assertEqual(
            self.client.get("/api/v1/documents/../pages/1/annotations").status_code, 404
        )

    def test_pdf_pages_use_their_own_dimensions_and_separate_annotations(self):
        buffer = io.BytesIO()
        Image.new("RGB", (400, 200), "white").save(
            buffer, "PDF", save_all=True, append_images=[Image.new("RGB", (200, 500), "white")]
        )
        document = self.client.post(
            "/api/v1/documents/upload",
            files={"file": ("two-pages.pdf", buffer.getvalue(), "application/pdf")},
        ).json()
        base = f"/api/v1/documents/{document['id']}/pages/2"
        page = self.client.get(base).json()
        self.assertNotEqual(
            (page["width"], page["height"]), (document["width"], document["height"])
        )
        self.assertEqual(page["page_number"], 2)
        body = self.body()
        body["symbols"][0].update(x=page["width"] - 20, y=page["height"] - 20, width=20, height=20)
        body["texts"] = []
        body["relations"] = []
        self.assertEqual(self.client.put(base + "/annotations", json=body).status_code, 200)
        self.assertEqual(
            self.client.get(f"/api/v1/documents/{document['id']}/pages/1/annotations").json()[
                "symbols"
            ],
            [],
        )
        tile = page["tile_url_template"].format(z=page["max_zoom"], x=0, y=0)
        self.assertEqual(self.client.get(tile).status_code, 200)
        self.assertEqual(
            self.client.get(f"/api/v1/documents/{document['id']}/pages/3").status_code, 404
        )

    def test_empty_page_can_be_saved_and_exported_as_negative_example(self):
        self.assertEqual(
            self.client.put(
                self.base, json=dict(revision=0, symbols=[], texts=[], relations=[])
            ).status_code,
            200,
        )
        with zipfile.ZipFile(io.BytesIO(self.client.get(self.base + "/export").content)) as zipped:
            label = next(name for name in zipped.namelist() if name.startswith("labels/"))
            self.assertEqual(zipped.read(label), b"")

    def test_labeled_filter_updates_after_save_clear_and_delete(self):
        self.assertEqual(self.client.get("/api/v1/documents?labeled=true").json(), [])
        self.client.put(self.base, json=self.body()).raise_for_status()
        fixtures.web.drawings.clear()
        labeled = self.client.get("/api/v1/documents?labeled=true").json()
        self.assertEqual(len(labeled), 1)
        self.assertEqual(labeled[0]["labeled_pages"], [1])
        self.assertEqual(labeled[0]["annotation_count"], 2)
        self.assertTrue(labeled[0]["is_labeled"])
        self.assertEqual(self.client.get("/api/v1/documents?labeled=false").json(), [])
        self.client.put(
            self.base, json=dict(revision=1, symbols=[], texts=[], relations=[])
        ).raise_for_status()
        self.assertEqual(self.client.get("/api/v1/documents?labeled=true").json(), [])
        self.client.delete(f"/api/v1/documents/{self.document['id']}").raise_for_status()
        self.assertEqual(self.client.get(self.base).status_code, 404)
