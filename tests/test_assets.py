"""Asset identity, live search and real PostgreSQL/MinIO attachment regressions."""

from __future__ import annotations

import copy
import hashlib
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import test_document_storage as fixtures
from fastapi.testclient import TestClient
from minio.error import S3Error
from psycopg import OperationalError

from app import asset_catalog as catalog
from app import document_storage as storage
from app import web_main as web


class TestOccurrenceExtraction(unittest.TestCase):
    def row(self):
        return dict(
            drawing_id="a" * 32,
            page_number=2,
            source="annotation",
            job_id="",
            metadata=dict(original_name="pid.pdf", project="Plant A"),
            data=dict(
                symbols=[dict(id="s1", label_id="pump", x=10, y=20, width=50, height=40)],
                texts=[dict(id="t1", text="P-101A", x=5, y=70, width=60, height=15)],
                relations=[dict(type="text_of", source="t1", target="s1")],
                classes=[dict(code="pump", name="Pump")],
            ),
        )

    def test_explicit_text_link_focuses_symbol_and_does_not_duplicate_ocr(self):
        items = list(catalog.extract_occurrences(self.row()))
        self.assertEqual(len(items), 1)
        self.assertEqual(
            (items[0]["tag"], items[0]["kind"], items[0]["equipment_type"]),
            ("P-101A", "symbol", "Pump"),
        )
        self.assertEqual(items[0]["box"]["x"], 10)

    def test_unlinked_ocr_is_searchable_but_not_guessed_to_be_a_symbol(self):
        row = self.row()
        row["data"]["relations"] = []
        symbol, item = catalog.extract_occurrences(row)
        self.assertEqual((symbol["tag"], symbol["symbol_code"]), ("", "pump"))
        self.assertEqual(item["kind"], "text")
        self.assertEqual(item["box"]["x"], 5)
        self.assertEqual(item["symbol_code"], "")

    def test_symbol_code_is_searchable_without_inventing_an_equipment_tag(self):
        row = self.row()
        row["data"]["texts"] = []
        row["data"]["relations"] = []
        row["data"]["symbols"][0]["label_id"] = "VALVES-019"
        row["data"]["classes"] = [dict(code="VALVES-019", name="GATE VALVE")]
        (item,) = catalog.extract_occurrences(row)
        self.assertEqual((item["tag"], item["symbol_code"]), ("", "VALVES-019"))
        self.assertEqual(item["equipment_type"], "GATE VALVE")
        self.assertEqual(item["box"]["x"], 10)

    def test_symbol_code_does_not_replace_explicit_or_linked_tags(self):
        row = self.row()
        row["data"]["symbols"][0]["label_id"] = "VALVES-019"
        for explicit, expected in ((None, "P-101A"), ("V-201", "V-201")):
            if explicit:
                row["data"]["symbols"][0]["tag"] = explicit
            (item,) = catalog.extract_occurrences(row)
            self.assertEqual((item["tag"], item["symbol_code"]), (expected, "VALVES-019"))

    def test_invalid_geometry_is_not_used_for_navigation(self):
        for value in (float("nan"), float("inf"), -1, None):
            row = self.row()
            row["data"]["symbols"][0]["width"] = value
            self.assertEqual(list(catalog.extract_occurrences(row)), [])

    def test_tag_normalization_preserves_meaning_and_handles_scan_dashes(self):
        self.assertEqual(catalog.normalize_tag(" p – 101a "), "P-101A")
        self.assertNotEqual(catalog.normalize_tag("P-101A"), catalog.normalize_tag("P-101B"))


@unittest.skipUnless(
    os.getenv("DOCUMENT_TEST_STORAGE") == "1",
    "Set DOCUMENT_TEST_STORAGE=1 for asset integration tests",
)
class TestAssetCatalog(unittest.TestCase):
    connection = fixtures.TestDocumentStorage.connection
    cleanup_storage = fixtures.TestDocumentStorage.cleanup_storage
    source = fixtures.TestDocumentStorage.source

    def setUp(self):
        fixtures.TestDocumentStorage.setUp(self)
        self.enterContext(patch.object(web, "init_library"))
        self.enterContext(patch.object(storage, "init_documents"))
        self.client = self.enterContext(TestClient(web.app))
        self.drawing = self.make_drawing()
        self.profile = dict(
            project="Plant A",
            area="Unit 1",
            tag="P-101A",
            name="Feed pump",
            equipment_type="Pump",
            notes="",
        )

    def make_drawing(self, project="Plant A", lifecycle="current"):
        id_, source, metadata = self.source()
        storage.save_source(
            id_, source, dict(metadata, project=project, lifecycle=lifecycle, revision_label="02")
        )
        data = TestOccurrenceExtraction().row()["data"]
        data.update(revision=1, saved_at=datetime.now(timezone.utc).isoformat())
        storage.save_annotation(id_, 2, data, 0)
        return id_

    def search(self, **params):
        response = self.client.get("/api/v1/asset-search", params=params)
        response.raise_for_status()
        return response.json()

    def create(self, **changes):
        response = self.client.post("/api/v1/assets", json={**self.profile, **changes})
        response.raise_for_status()
        return response.json()

    def ref(self, drawing=None):
        item = next(
            item
            for item in self.search(include_superseded=True)["items"]
            if item["drawing_id"] == (drawing or self.drawing)
        )
        return {key: item[key] for key in catalog.OccurrenceRef.model_fields}

    def detail(self, asset):
        response = self.client.get(f"/api/v1/assets/{asset['id']}")
        response.raise_for_status()
        return response.json()

    def test_search_is_partial_scoped_paginated_and_defaults_to_current(self):
        self.make_drawing(project="Plant B")
        self.make_drawing(lifecycle="superseded")
        self.assertEqual(self.search(q="p – 101")["total"], 2)
        self.assertEqual(self.search(q="P-101", project="plant a")["total"], 1)
        self.assertEqual(self.search(q="101", include_superseded=True)["total"], 3)
        page = self.search(limit=1, offset=1)
        self.assertEqual((len(page["items"]), page["total"]), (1, 2))
        self.assertEqual(self.search(q="missing")["items"], [])

    def test_search_finds_saved_symbol_codes_with_and_without_equipment_tags(self):
        data = storage.read_annotation(self.drawing, 2)
        data["symbols"][0]["label_id"] = "VALVES-019"
        data["symbols"].append(
            dict(id="s2", label_id="VALVES-019", x=100, y=200, width=30, height=40)
        )
        storage.save_annotation(self.drawing, 2, data, 1)
        result = self.search(q=" valves – 019 ", project="plant a", limit=1)
        self.assertEqual((result["total"], len(result["items"])), (2, 1))
        second = self.search(q="valves-019", offset=1, limit=1)
        items = result["items"] + second["items"]
        self.assertEqual({item["tag"] for item in items}, {"", "P-101A"})
        self.assertTrue(all(item["symbol_code"] == "VALVES-019" for item in items))
        self.assertEqual(self.search(q="VALVES-0")["total"], 2)
        self.assertEqual(self.search(q="P-101A")["total"], 1)
        self.assertEqual(self.search(q="VALVES-019", project="other")["total"], 0)
        self.assertEqual(self.search(q="VALVES-020")["total"], 0)
        untagged = next(item for item in items if not item["tag"])
        ref = {key: untagged[key] for key in catalog.OccurrenceRef.model_fields}
        response = self.client.post("/api/v1/assets", json={**self.profile, "occurrence": ref})
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(len(self.detail(response.json())["occurrences"]), 1)

    def test_profile_identity_is_scoped_and_normalized(self):
        self.create()
        duplicate = self.client.post(
            "/api/v1/assets",
            json={**self.profile, "project": " plant a ", "area": "unit 1", "tag": "p – 101a"},
        )
        self.assertEqual(duplicate.status_code, 409)
        self.create(project="Plant B")
        self.create(area="Unit 2")
        response = self.client.get("/api/v1/assets", params=dict(q="feed", project="Plant A"))
        self.assertEqual(response.json()["total"], 2)
        self.assertEqual(
            self.client.post("/api/v1/assets", json={**self.profile, "tag": "  "}).status_code, 422
        )

    def test_independent_profile_for_untagged_unassigned_symbol_leaves_source_unchanged(self):
        drawing = self.make_drawing(project="")
        data = storage.read_annotation(drawing, 2)
        data.update(texts=[], relations=[])
        data["symbols"][0]["label_id"] = "VALVES-019"
        storage.save_annotation(drawing, 2, data, 1)
        (item,) = self.search(q="VALVES-019")["items"]
        self.assertEqual((item["tag"], item["project"]), ("", ""))
        asset = self.create(project="HaNoi", area="HN", tag="xy-10", name="MAY NO")
        detail = self.detail(asset)
        self.assertEqual(detail["tag"], "xy-10")
        self.assertEqual(detail["occurrences"], [])
        self.assertEqual(storage.read_annotation(drawing, 2), data)
        self.assertEqual(storage.get_document(drawing)["project"], "")

    def test_invalid_creation_links_do_not_leave_partial_profiles(self):
        for ref, status in ((dict(self.ref(), tag=""), 409), (self.ref(), 422)):
            response = self.client.post(
                "/api/v1/assets",
                json={**self.profile, "project": "HaNoi", "tag": "xy-10", "occurrence": ref},
            )
            self.assertEqual(response.status_code, status, response.text)
            self.assertEqual(self.client.get("/api/v1/assets").json()["total"], 0)

    def untagged_symbol(self):
        drawing = self.make_drawing(project="")
        data = storage.read_annotation(drawing, 2)
        data.update(texts=[], relations=[])
        data["symbols"][0]["label_id"] = "VALVES-019"
        storage.save_annotation(drawing, 2, data, 1)
        return drawing, data, self.ref(drawing)

    def test_create_and_manually_link_untagged_symbol_without_changing_source(self):
        drawing, data, ref = self.untagged_symbol()
        asset = self.create(project="HN", tag="XY-01", occurrence=ref)
        (location,) = self.detail(asset)["occurrences"]
        self.assertEqual(location["drawing_id"], drawing)
        self.assertEqual(location["box"]["x"], 10)
        self.assertEqual((location["tag"], location["symbol_code"]), ("", "VALVES-019"))
        self.assertEqual((location["asset_tag"], location["asset_project"]), ("XY-01", "HN"))
        self.assertEqual(self.search(q="XY-01", project="HN")["total"], 1)
        self.assertEqual(storage.read_annotation(drawing, 2), data)
        self.assertEqual(storage.get_document(drawing)["project"], "")

    def test_existing_profile_can_link_unassigned_symbol_and_reopen_its_location(self):
        drawing, _, ref = self.untagged_symbol()
        asset = self.create(project="HN", tag="XY-01")
        url = f"/api/v1/assets/{asset['id']}/occurrences"
        response = self.client.post(url, json=ref)
        self.assertEqual(response.status_code, 201, response.text)
        (location,) = self.detail(asset)["occurrences"]
        self.assertEqual((location["drawing_id"], location["page_number"]), (drawing, 2))
        self.assertEqual(self.client.post(url, json=ref).status_code, 201)
        self.assertEqual(len(self.detail(asset)["occurrences"]), 1)
        other = self.create(project="HN", tag="XY-02")
        self.assertEqual(
            self.client.post(f"/api/v1/assets/{other['id']}/occurrences", json=ref).status_code,
            409,
        )
        self.client.delete(f"{url}/{location['link_id']}").raise_for_status()
        self.assertEqual(self.detail(asset)["occurrences"], [])
        self.assertEqual(self.search(q="XY-01")["total"], 0)

    def test_manual_links_validate_symbol_code_and_become_stale_after_source_changes(self):
        drawing, data, ref = self.untagged_symbol()
        asset = self.create(project="HN", tag="XY-01")
        url = f"/api/v1/assets/{asset['id']}/occurrences"
        self.assertEqual(self.client.post(url, json={**ref, "symbol_code": ""}).status_code, 422)
        self.assertEqual(
            self.client.post(url, json={**ref, "symbol_code": "VALVES-020"}).status_code, 409
        )
        self.client.post(url, json=ref).raise_for_status()
        data["symbols"][0]["label_id"] = "VALVES-020"
        storage.save_annotation(drawing, 2, data, 1)
        detail = self.detail(asset)
        self.assertEqual(detail["occurrences"], [])
        self.assertEqual(len(detail["stale_links"]), 1)
        self.assertEqual(self.search(q="XY-01")["total"], 0)

    def test_manual_link_becomes_stale_when_drawing_gets_a_different_project(self):
        drawing, _, ref = self.untagged_symbol()
        asset = self.create(project="HN", tag="XY-01", occurrence=ref)
        storage.update_document(drawing, dict(project="Other plant"))
        self.assertEqual(self.detail(asset)["occurrences"], [])
        self.assertEqual(len(self.detail(asset)["stale_links"]), 1)

    def test_schema_upgrade_preserves_existing_tagged_links(self):
        asset = self.create(occurrence=self.ref())
        with storage.connection() as db:
            db.execute("ALTER TABLE plant_asset_occurrences DROP COLUMN source_symbol_code")
            catalog.init_tables(db)
            catalog.init_tables(db)
        self.assertEqual(len(self.detail(asset)["occurrences"]), 1)

    def test_many_drawings_share_one_asset_and_links_are_explicit(self):
        second = self.make_drawing()
        asset = self.create(occurrence=self.ref())
        self.assertEqual(sum(bool(item["asset_id"]) for item in self.search()["items"]), 1)
        response = self.client.post(
            f"/api/v1/assets/{asset['id']}/occurrences", json=self.ref(second)
        )
        self.assertEqual(response.status_code, 201, response.text)
        detail = self.detail(asset)
        self.assertEqual(len(detail["occurrences"]), 2)
        link_id = detail["occurrences"][0]["link_id"]
        self.client.delete(f"/api/v1/assets/{asset['id']}/occurrences/{link_id}").raise_for_status()
        self.assertEqual(len(self.detail(asset)["occurrences"]), 1)

    def test_link_rejects_other_project_and_other_asset_and_stale_search(self):
        asset = self.create(occurrence=self.ref())
        other = self.create(area="Unit 2")
        ref = self.ref()
        self.assertEqual(
            self.client.post(f"/api/v1/assets/{other['id']}/occurrences", json=ref).status_code, 409
        )
        ref["tag"] = "CHANGED"
        self.assertEqual(
            self.client.post(f"/api/v1/assets/{other['id']}/occurrences", json=ref).status_code, 409
        )
        other_project = self.make_drawing(project="Plant B")
        self.assertEqual(
            self.client.post(
                f"/api/v1/assets/{asset['id']}/occurrences", json=self.ref(other_project)
            ).status_code,
            422,
        )

    def test_changed_tag_is_not_silently_attached_to_an_existing_asset(self):
        asset = self.create(occurrence=self.ref())
        data = storage.read_annotation(self.drawing, 2)
        data["texts"][0]["text"] = "P-102"
        data["revision"] = 2
        storage.save_annotation(self.drawing, 2, data, 1)
        (item,) = self.search()["items"]
        self.assertEqual(item["tag"], "P-102")
        self.assertIsNone(item["asset_id"])
        detail = self.detail(asset)
        self.assertEqual(len(detail["stale_links"]), 1)
        self.assertEqual(detail["occurrences"], [])
        storage.delete_document(self.drawing)
        self.assertEqual(self.detail(asset)["stale_links"], [])

    def test_edits_require_current_version_and_duplicate_scope_is_rejected(self):
        asset = self.create()
        url = f"/api/v1/assets/{asset['id']}"
        body = {**self.profile, "version": 1, "notes": "Serviced"}
        updated = self.client.put(url, json=body)
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["version"], 2)
        self.assertEqual(self.client.put(url, json=body).status_code, 409)
        self.create(area="Unit 2")
        self.assertEqual(
            self.client.put(url, json={**body, "version": 2, "area": "Unit 2"}).status_code, 409
        )

    def test_review_search_survives_process_state_and_reused_ids_do_not_relink(self):
        data = dict(
            symbols=[dict(id="s-0", tag="V-201", type="Valve", x=50, y=60, width=30, height=30)],
            texts=[],
            lines=[],
            topology_edges=[],
            review=dict(saved_at=datetime.now(timezone.utc).isoformat()),
        )
        catalog.save_review_scene(self.drawing, "run-1", data)
        (item,) = self.search(q="V-201")["items"]
        ref = {key: item[key] for key in catalog.OccurrenceRef.model_fields}
        asset = self.create(tag="V-201", occurrence=ref)
        web.jobs.clear()
        self.assertEqual(len(self.detail(asset)["occurrences"]), 1)
        catalog.save_review_scene(self.drawing, "run-2", copy.deepcopy(data))
        (item,) = self.search(q="V-201")["items"]
        self.assertIsNone(item["asset_id"])
        self.assertEqual(len(self.detail(asset)["stale_links"]), 1)

    def test_review_save_endpoint_indexes_the_trusted_drawing(self):
        root = self.root / "run"
        root.mkdir()
        result = root / "scene.json"
        result.write_text("{}")
        job_id = "asset-test-job"
        self.addCleanup(web.jobs.pop, job_id, None)
        web.jobs[job_id] = web.PipelineJob(
            job_id=job_id, drawing_id=self.drawing, status="COMPLETED", result_path=result
        )
        data = dict(
            symbols=[dict(id="s1", tag="P-999", x=1, y=1, width=10, height=10)],
            texts=[],
            lines=[],
            topology_edges=[],
            source=dict(drawing_id="untrusted", page_number=999),
        )
        response = self.client.post(f"/api/v1/jobs/{job_id}/final-results", json=data)
        self.assertEqual(response.status_code, 200, response.text)
        (item,) = self.search(q="P-999")["items"]
        self.assertEqual((item["drawing_id"], item["page_number"]), (self.drawing, 1))

    def test_document_upload_download_links_and_delete(self):
        asset = self.create()
        url = f"/api/v1/assets/{asset['id']}/documents"
        content = b"test datasheet bytes"
        response = self.client.post(
            url + "/upload",
            data=dict(category="datasheet", title="Pump datasheet"),
            files=dict(file=("thông số.pdf", content, "application/pdf")),
        )
        self.assertEqual(response.status_code, 201, response.text)
        id_ = response.json()["id"]
        downloaded = self.client.get(url + f"/{id_}/download")
        self.assertEqual(downloaded.content, content)
        self.assertIn("attachment;", downloaded.headers["content-disposition"])
        document = self.detail(asset)["documents"][0]
        self.assertEqual(document["sha256"], hashlib.sha256(content).hexdigest())
        self.client.post(
            url + "/links",
            json=dict(title="Manual", category="manual", url="https://docs.example.com/manual.pdf"),
        ).raise_for_status()
        self.assertEqual(len(self.detail(asset)["documents"]), 2)
        self.client.delete(url + f"/{id_}").raise_for_status()
        self.assertEqual(self.client.get(url + f"/{id_}/download").status_code, 404)
        self.assertEqual(
            list(storage.client().list_objects(self.bucket, prefix="assets/", recursive=True)), []
        )

    def test_attachment_rejects_unsafe_links_unsupported_empty_and_large_files(self):
        asset = self.create()
        url = f"/api/v1/assets/{asset['id']}/documents"
        for value in (
            "javascript:alert(1)",
            "file:///etc/passwd",
            "https://user:password@example.com/doc",
            "https://",
        ):
            self.assertEqual(
                self.client.post(url + "/links", json=dict(title="Manual", url=value)).status_code,
                422,
            )
        self.assertEqual(
            self.client.post(url + "/upload", files=dict(file=("x.html", b"x"))).status_code, 415
        )
        self.assertEqual(
            self.client.post(url + "/upload", files=dict(file=("x.pdf", b""))).status_code, 422
        )
        with patch.object(catalog, "MAX_FILE_BYTES", 2):
            self.assertEqual(
                self.client.post(url + "/upload", files=dict(file=("x.pdf", b"xxx"))).status_code,
                413,
            )
        self.assertEqual(self.detail(asset)["documents"], [])

    def test_failed_object_delete_keeps_document_for_retry(self):
        asset = self.create()
        url = f"/api/v1/assets/{asset['id']}/documents"
        id_ = self.client.post(url + "/upload", files=dict(file=("x.pdf", b"data"))).json()["id"]
        with patch.object(storage, "client") as client:
            client.return_value.remove_object.side_effect = S3Error(
                "AccessDenied", "denied", "x", "x", "x", None
            )
            self.assertEqual(self.client.delete(url + f"/{id_}").status_code, 503)
        self.assertEqual(len(self.detail(asset)["documents"]), 1)

    def test_failed_database_commit_cleans_uploaded_object(self):
        asset = self.create()
        real_connection = storage.connection

        class FailingCommit:
            def __enter__(self):
                self.db = real_connection()
                return self

            def __exit__(self, *args):
                self.db.rollback()
                self.db.close()

            def execute(self, *args, **kwargs):
                return self.db.execute(*args, **kwargs)

            def commit(self):
                raise OperationalError("commit failed")

        with patch.object(storage, "connection", FailingCommit):
            response = self.client.post(
                f"/api/v1/assets/{asset['id']}/documents/upload",
                files=dict(file=("x.pdf", b"data")),
            )
            self.assertEqual(response.status_code, 503)
        self.assertEqual(
            list(storage.client().list_objects(self.bucket, prefix="assets/", recursive=True)), []
        )

    def test_schema_initialization_is_repeatable_and_data_remains(self):
        asset = self.create(occurrence=self.ref())
        with storage.connection() as db:
            catalog.init_tables(db)
            catalog.init_tables(db)
        self.assertEqual(len(self.detail(asset)["occurrences"]), 1)
