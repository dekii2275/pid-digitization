"""Durable page editing and semantic checks on exported, reloaded DXF files."""

from __future__ import annotations

import io
import json
import os
import unittest
from unittest.mock import patch

import ezdxf
import test_document_storage as fixtures
import test_web_main as web_fixtures
from ezdxf import bbox
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import document_storage as storage
from app import drawing_editor as editor
from app import web_main as web
from app.cad_export import scene_to_dxf


def example_scene():
    return dict(
        symbols=[
            dict(
                id="s1", type="Pump", tag="P-101A", x=100, y=100, width=80, height=60, rotation=90
            ),
            dict(id="s2", type="Valve", tag="V-101", x=300, y=100, width=40, height=40),
        ],
        texts=[dict(id="t1", text="Đường cấp nước", x=100, y=200, width=180, height=20)],
        lines=[dict(id="l1", points=[[180, 130], [250, 130], [250, 120], [300, 120]])],
        topology_edges=[dict(id="e1", source="s1", target="s2")],
        cad_settings=dict(units="mm", units_per_pixel=0.5),
    )


class TestDxfGeometry(unittest.TestCase):
    def load(self, scene=None):
        scene = editor.normalize_scene(scene or example_scene(), "a" * 32, 2, 800, 600, "P&ID.pdf")
        return ezdxf.read(io.StringIO(scene_to_dxf(scene, "job_test").decode("utf-8")))

    def test_blocks_attributes_layers_coordinate_scale_rotation_and_ids(self):
        doc = self.load()
        self.assertFalse(doc.audit().has_errors)
        self.assertEqual(doc.units, 4)
        blocks = list(doc.modelspace().query("INSERT"))
        self.assertEqual(len(blocks), 2)
        pump = next(block for block in blocks if block.get_attrib_text("EID") == "s1")
        self.assertEqual(pump.get_attrib_text("TAG"), "P-101A")
        self.assertAlmostEqual(pump.dxf.insert.x, 70)
        self.assertAlmostEqual(pump.dxf.insert.y, 235)
        self.assertEqual(pump.dxf.rotation, -90)
        self.assertTrue(list(doc.blocks[pump.dxf.name].query("CIRCLE")))
        metadata = json.loads("".join(tag.value for tag in pump.get_xdata("VPI_PID")))
        self.assertEqual(
            (metadata["id"], metadata["page_number"], metadata["generation"]), ("s1", 2, "job_test")
        )
        (line,) = doc.modelspace().query('LWPOLYLINE[layer=="PID_PIPES"]')
        self.assertEqual(
            [(point[0], point[1]) for point in line.get_points()],
            [(90, 235), (125, 235), (125, 240), (150, 240)],
        )
        self.assertTrue(doc.layers.get("PID_CONNECTIONS").is_off())
        (text,) = doc.modelspace().query("TEXT")
        self.assertEqual(text.dxf.text, "Đường cấp nước")
        self.assertEqual(len(doc.modelspace().query("IMAGE")), 0)

    def test_line_formats_signal_layers_unicode_and_multiline_text(self):
        scene = example_scene()
        scene["cad_settings"] = dict(units="inch", units_per_pixel=2)
        scene["lines"] = [
            dict(id="l2", start=[1, 2], end=[3, 4], line_type="signal"),
            dict(id="l3", x1=5, y1=6, x2=7, y2=8),
        ]
        scene["texts"][0]["text"] = "Dòng 1\nNội dung \\P {không định dạng}"
        scene["symbols"][0]["tag"] = "BƠM-101"
        doc = self.load(scene)
        self.assertFalse(doc.audit().has_errors)
        self.assertEqual(doc.units, 1)
        self.assertEqual(len(doc.modelspace().query('LWPOLYLINE[layer=="PID_SIGNALS"]')), 1)
        (mtext,) = doc.modelspace().query("MTEXT")
        self.assertIn("\\\\P", mtext.text)
        self.assertIn("\\{", mtext.text)
        self.assertIn(
            "BƠM-101",
            [entity.get_attrib_text("TAG") for entity in doc.modelspace().query("INSERT")],
        )

    def test_bad_geometry_and_dangling_relations_are_rejected(self):
        for mutate in (
            lambda data: data["symbols"][0].update(x="NaN"),
            lambda data: data["symbols"][0].update(rotation="Infinity"),
            lambda data: data["lines"][0].update(points=[[0, 0], [900, 0]]),
            lambda data: data["topology_edges"][0].update(target="missing"),
        ):
            scene = example_scene()
            mutate(scene)
            with self.assertRaises(HTTPException) as context:
                editor.normalize_scene(scene, "a" * 32, 1, 800, 600, "pid.png")
            self.assertEqual(context.exception.status_code, 422)

    def test_signal_lines_keep_a_scaled_dash_pattern_across_vertices(self):
        scene = example_scene()
        scene["lines"][0]["line_type"] = "signal"
        doc = self.load(scene)
        self.assertFalse(doc.audit().has_errors)
        layer = doc.layers.get("PID_SIGNALS")
        self.assertNotEqual(layer.dxf.linetype.lower(), "continuous")
        pattern = doc.linetypes.get(layer.dxf.linetype).pattern_tags.tags
        self.assertEqual([tag.value for tag in pattern if tag.code == 49], [4, -2])
        (line,) = doc.modelspace().query('LWPOLYLINE[layer=="PID_SIGNALS"]')
        self.assertTrue(line.dxf.flags & 128)
        self.assertEqual(doc.layers.get("PID_PIPES").dxf.linetype.lower(), "continuous")

    def test_304_symbol_classes_keep_distinct_cad_shapes(self):
        scene = example_scene()
        scene.update(symbols=[], texts=[], lines=[], topology_edges=[])
        for index, (code, name) in enumerate(
            (
                ("LC-001", "PROCESS/INSTRUMENT SIGNAL LINE WITHIN A UNIT"),
                ("VALVES-012", "CHECK/NON RETURN VALVE"),
                ("VALVES-019", "GATE VALVE"),
                ("VALVES-020", "GLOBE VALVE"),
            )
        ):
            scene["symbols"].append(
                dict(
                    id=code,
                    label_id=code,
                    type=name,
                    x=50 + index * 100,
                    y=100,
                    width=60,
                    height=40,
                )
            )
        doc = self.load(scene)
        self.assertFalse(doc.audit().has_errors)
        inserts = {item.get_attrib_text("EID"): item for item in doc.modelspace().query("INSERT")}
        connector = inserts["LC-001"]
        self.assertEqual(connector.dxf.layer, "PID_CONNECTORS")
        self.assertFalse(doc.layers.get("PID_CONNECTORS").is_off())
        self.assertEqual(len(doc.blocks[connector.dxf.name].query("CIRCLE")), 0)
        (outline,) = doc.blocks[connector.dxf.name].query("LWPOLYLINE")
        self.assertEqual(len(outline), 5)
        check = doc.blocks[inserts["VALVES-012"].dxf.name]
        self.assertEqual(len(check.query("LINE")), 1)
        globe = doc.blocks[inserts["VALVES-020"].dxf.name]
        self.assertEqual(len(globe.query("HATCH")), 1)
        gate = doc.blocks[inserts["VALVES-019"].dxf.name]
        self.assertEqual(len(gate.query("HATCH")), 0)

    def test_manual_cad_shape_is_preserved_over_automatic_classification(self):
        self.assertEqual(editor.cad_kind(dict(label_id="LC-001", cad_kind="other")), "other")
        self.assertEqual(editor.cad_kind(dict(type="GLOBE VALVE")), "globe_valve")
        self.assertEqual(editor.cad_kind(dict(type="CHECK VALVE")), "check_valve")

    def test_multiline_text_keeps_content_and_stays_inside_source_height(self):
        scene = example_scene()
        scene.update(symbols=[], lines=[], topology_edges=[])
        scene["texts"] = [
            dict(id="note", text="Dòng 1\nDòng 2\nDòng 3", x=100, y=200, width=180, height=40)
        ]
        doc = self.load(scene)
        (text,) = doc.modelspace().query("MTEXT")
        self.assertEqual(text.plain_text(), "Dòng 1\nDòng 2\nDòng 3")
        bounds = bbox.extents(doc.modelspace())
        self.assertLessEqual(bounds.size.y, 40 * 0.5)
        self.assertEqual((text.dxf.insert.x, text.dxf.insert.y), (50, 200))


@unittest.skipUnless(
    os.getenv("DOCUMENT_TEST_STORAGE") == "1",
    "Set DOCUMENT_TEST_STORAGE=1 for editor integration tests",
)
class TestDrawingEditor(unittest.TestCase):
    connection = fixtures.TestDocumentStorage.connection
    cleanup_storage = fixtures.TestDocumentStorage.cleanup_storage
    upload = web_fixtures.TestDrawingReview.upload
    upload_vector_pdf = web_fixtures.TestDrawingReview.upload_vector_pdf

    def setUp(self):
        fixtures.TestDocumentStorage.setUp(self)
        self.enterContext(patch.object(web, "init_library"))
        self.enterContext(patch.object(storage, "init_documents"))
        self.import_legacy = editor.import_legacy_results
        self.enterContext(patch.object(editor, "import_legacy_results"))
        for name in ("APP_ROOT", "PREVIEW_ROOT", "TILE_ROOT", "PIPELINE_ARTIFACTS_ROOT"):
            path = self.root / name
            path.mkdir()
            self.enterContext(patch.object(web, name, path))
        self.client = self.enterContext(TestClient(web.app))
        self.document = self.upload().json()
        self.base = f"/api/v1/documents/{self.document['id']}/pages/1/review-scene"
        self.addCleanup(web.jobs.clear)
        self.addCleanup(web.drawings.clear)

    def get_scene(self, **params):
        response = self.client.get(self.base, params=params)
        response.raise_for_status()
        return response.json()

    def save(self, scene=None, state=None):
        state = state or self.get_scene()
        return self.client.put(
            self.base,
            json=dict(
                version=state["version"],
                generation=state["generation"],
                scene=scene or example_scene(),
            ),
        )

    def processed(self, job="job_one", scene=None):
        editor.save_processed_scene(self.document["id"], 1, job, scene or example_scene())

    def test_manual_save_reopens_without_jobs_and_rejects_stale_writes(self):
        empty = self.get_scene()
        self.assertEqual((empty["origin"], empty["version"]), ("empty", 0))
        response = self.save(state=empty)
        self.assertEqual(response.status_code, 200, response.text)
        web.jobs.clear()
        web.drawings.clear()
        reopened = self.get_scene()
        self.assertEqual((reopened["origin"], reopened["version"]), ("review", 1))
        self.assertEqual(reopened["scene"]["symbols"][0]["tag"], "P-101A")
        self.assertEqual(reopened["scene"]["source"]["drawing_id"], self.document["id"])
        self.assertEqual(self.save(state=empty).status_code, 409)
        self.assertEqual(self.save(state=reopened).json()["version"], 2)

    def test_processing_is_durable_and_new_ai_does_not_overwrite_review(self):
        self.processed()
        original = self.get_scene()
        self.assertEqual(original["origin"], "processed")
        edited = example_scene()
        edited["symbols"][0]["tag"] = "P-EDITED"
        self.save(edited, original).raise_for_status()
        self.processed("job_two")
        reopened = self.get_scene()
        self.assertEqual(reopened["scene"]["symbols"][0]["tag"], "P-EDITED")
        latest_ai = self.get_scene(origin="processed")
        self.assertEqual(latest_ai["generation"], "job_two")
        self.assertEqual(latest_ai["version"], 1)
        self.assertEqual(latest_ai["scene"]["symbols"][0]["tag"], "P-101A")

    def test_replaced_unsaved_ai_source_is_rejected(self):
        self.processed()
        original = self.get_scene()
        self.processed("job_two")
        self.assertEqual(self.save(state=original).status_code, 409)

    def test_saved_annotations_can_seed_an_editable_scene(self):
        data = dict(
            revision=1,
            saved_at="2026-10-18T00:00:00+00:00",
            symbols=[dict(id="s", label_id="pump", x=10, y=10, width=40, height=40)],
            texts=[dict(id="t", text="P-202", x=10, y=60, width=50, height=10)],
            relations=[dict(id="r", type="text_of", source="t", target="s")],
            classes=[dict(code="pump", name="Pump", category="Pump")],
        )
        storage.save_annotation(self.document["id"], 1, data, 0)
        loaded = self.get_scene()
        self.assertEqual(loaded["origin"], "annotations")
        self.assertEqual(loaded["scene"]["symbols"][0]["tag"], "P-202")
        self.save(loaded["scene"], loaded).raise_for_status()
        self.assertEqual(storage.read_annotation(self.document["id"], 1), data)

    def test_export_uses_saved_version_and_filename_and_valid_dxf(self):
        self.assertEqual(
            self.client.get(self.base + "/export.dxf", params=dict(version=1)).status_code, 404
        )
        self.save().raise_for_status()
        response = self.client.get(self.base + "/export.dxf", params=dict(version=1))
        self.assertEqual(response.status_code, 200, response.text)
        doc = ezdxf.read(io.StringIO(response.content.decode("utf-8")))
        self.assertFalse(doc.audit().has_errors)
        self.assertIn("-p1-v1.dxf", response.headers["content-disposition"])
        self.save().raise_for_status()
        self.assertEqual(
            self.client.get(self.base + "/export.dxf", params=dict(version=1)).status_code, 409
        )

    def test_invalid_geometry_duplicates_or_source_identity_do_not_corrupt_saved_data(self):
        self.save().raise_for_status()
        invalid = example_scene()
        invalid["symbols"][0]["x"] = -1
        self.assertEqual(self.save(invalid).status_code, 422)
        duplicate = example_scene()
        duplicate["symbols"][1]["id"] = "s1"
        self.assertEqual(self.save(duplicate).status_code, 422)
        self.assertEqual(self.get_scene()["version"], 1)
        data = example_scene()
        data["source"] = dict(drawing_id="wrong", page_number=99, width=1, height=1)
        self.save(data).raise_for_status()
        self.assertEqual(self.get_scene()["scene"]["source"]["width"], 800)

    def test_pages_are_independent_and_pipeline_can_target_page_two(self):
        document = self.upload_vector_pdf()
        page1 = f"/api/v1/documents/{document['id']}/pages/1/review-scene"
        page2 = page1.replace("/pages/1/", "/pages/2/")
        loaded = self.client.get(page2).json()
        tiny = dict(
            symbols=[dict(id="s", tag="PAGE-2", type="Pump", x=10, y=10, width=20, height=20)],
            texts=[],
            lines=[],
            topology_edges=[],
        )
        saved = self.client.put(
            page2, json=dict(version=0, generation=loaded["generation"], scene=tiny)
        )
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(self.client.get(page1).json()["version"], 0)
        with patch.object(web.threading.Thread, "start"):
            response = self.client.post(f"/api/v1/documents/{document['id']}/run-all?page_number=2")
        self.assertEqual(response.status_code, 202, response.text)
        self.assertEqual(response.json()["page_number"], 2)
        self.assertEqual(
            self.client.post(
                f"/api/v1/documents/{document['id']}/run-all?page_number=3"
            ).status_code,
            404,
        )
        self.assertEqual(self.client.get(page2.replace("/pages/2/", "/pages/3/")).status_code, 404)

    def test_legacy_artifacts_import_only_once_without_replacing_edits(self):
        path = self.root / "legacy" / self.document["id"] / "job_old" / "editor"
        path.mkdir(parents=True)
        (path / "scene.json").write_text(json.dumps(example_scene()))
        final = example_scene()
        final["symbols"][0]["tag"] = "LEGACY-FINAL"
        (path / "final-scene.json").write_text(json.dumps(final))
        self.import_legacy(self.root / "legacy")
        self.assertEqual(self.get_scene()["scene"]["symbols"][0]["tag"], "LEGACY-FINAL")
        self.save().raise_for_status()
        self.import_legacy(self.root / "legacy")
        self.assertEqual(self.get_scene()["version"], 2)

    def test_delete_document_cascades_all_page_results(self):
        self.processed()
        self.save().raise_for_status()
        self.client.delete(f"/api/v1/documents/{self.document['id']}").raise_for_status()
        self.assertEqual(self.client.get(self.base).status_code, 404)
        with storage.connection() as db:
            for table in ("drawing_review_scenes", "drawing_processed_scenes"):
                self.assertIsNone(
                    db.execute(
                        f"SELECT 1 FROM {table} WHERE drawing_id = %s", (self.document["id"],)
                    ).fetchone()
                )
