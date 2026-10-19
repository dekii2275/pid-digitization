"""Page workflow, organization, thumbnails and negative-page regressions."""

import io
import unittest

import test_annotations as annotation_fixtures
import test_web_main as fixtures
from PIL import Image


class TestDataManagement(unittest.TestCase):
    upload = fixtures.TestDrawingReview.upload
    upload_vector_pdf = fixtures.TestDrawingReview.upload_vector_pdf
    body = annotation_fixtures.TestAnnotations.body

    def setUp(self):
        annotation_fixtures.TestAnnotations.setUp(self)
        self.document_url = f"/api/v1/documents/{self.document['id']}"

    def change_status(self, status, document=None, page=1):
        document = document or self.client.get(self.document_url).json()
        workflow = document["page_workflows"].get(str(page), {})
        return self.client.put(
            f"/api/v1/documents/{document['id']}/pages/{page}/status",
            json={
                "status": status,
                "revision": workflow.get("revision", 0),
                "annotation_revision": workflow.get("annotation_revision", 0),
            },
        )

    def test_four_states_negative_page_and_restart(self):
        self.assertEqual(self.document["completed_page_count"], 0)
        document = self.document
        for status in ("in_progress", "pending_review", "completed"):
            response = self.change_status(status, document)
            self.assertEqual(response.status_code, 200, response.text)
            document = response.json()
            self.assertEqual(document["page_workflows"]["1"]["status"], status)
        self.assertEqual(document["completed_page_count"], 1)
        self.assertFalse(document["is_labeled"])
        fixtures.web.drawings.clear()
        self.assertEqual(self.client.get(self.document_url).json(), document)
        self.assertEqual(self.client.get("/api/v1/documents").json()[0]["completed_page_count"], 1)
        # Exporting a checked negative page must not reopen it just because its
        # first empty annotation file is being saved.
        self.client.put(
            self.base, json=dict(revision=0, symbols=[], texts=[], relations=[])
        ).raise_for_status()
        self.assertEqual(self.client.get(self.document_url).json()["completed_page_count"], 1)
        self.assertEqual(self.change_status("not_started").json()["completed_page_count"], 0)

    def test_workflow_rejects_invalid_page_state_and_stale_versions(self):
        old = self.document
        self.change_status("in_progress").raise_for_status()
        self.assertEqual(self.change_status("completed", old).status_code, 409)
        self.assertEqual(self.change_status("unknown").status_code, 422)
        self.assertEqual(self.change_status("completed", page=0).status_code, 404)
        self.assertEqual(self.change_status("completed", page=2).status_code, 404)
        self.assertEqual(
            self.client.put(
                "/api/v1/documents/" + "a" * 32 + "/pages/1/status",
                json={
                    "status": "completed",
                    "revision": 0,
                    "annotation_revision": 0,
                },
            ).status_code,
            404,
        )

    def test_annotation_edit_reopens_completed_page_but_unchanged_save_preserves_state(self):
        body = self.body()
        self.client.put(self.base, json=body).raise_for_status()
        current = self.client.get(self.document_url).json()
        self.assertEqual(current["page_workflows"]["1"]["status"], "in_progress")
        completed = self.change_status("completed").json()
        body["revision"] = 1
        self.client.put(self.base, json=body).raise_for_status()
        self.assertEqual(self.client.get(self.document_url).json()["completed_page_count"], 1)
        # A save advanced the annotation revision, even with identical content.
        self.assertEqual(self.change_status("pending_review", completed).status_code, 409)
        body["revision"] = 2
        body["texts"][0]["text"] = "P-102"
        self.client.put(self.base, json=body).raise_for_status()
        document = self.client.get(self.document_url).json()
        self.assertEqual(document["completed_page_count"], 0)
        self.assertEqual(document["page_workflows"]["1"]["status"], "in_progress")

    def test_pages_are_independent_and_thumbnail_keeps_annotation_coordinates(self):
        document = self.upload_vector_pdf()
        response = self.change_status("completed", document, page=2)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["completed_page_count"], 1)
        self.assertNotIn("1", response.json()["page_workflows"])
        url = f"/api/v1/documents/{document['id']}/pages/2/thumbnail.jpg"
        thumbnail = self.client.get(url)
        self.assertEqual(thumbnail.status_code, 200)
        self.assertEqual(thumbnail.headers["content-type"], "image/jpeg")
        with Image.open(io.BytesIO(thumbnail.content)) as image:
            self.assertLessEqual(max(image.size), 320)
            self.assertGreater(image.width, image.height)
        page = self.client.get(f"/api/v1/documents/{document['id']}/pages/2").json()
        self.assertEqual((page["width"], page["height"]), (288, 144))
        self.assertEqual(self.client.get(url.replace("/2/", "/3/")).status_code, 404)
        image_thumb = self.client.get(self.document_url + "/pages/1/thumbnail.jpg")
        with Image.open(io.BytesIO(image_thumb.content)) as image:
            self.assertEqual(image.size, (320, 240))

    def test_organization_normalizes_and_survives_status_annotation_and_restart(self):
        changes = dict(
            project=" Nhà máy A ", drawing_set=" P&ID 01 ", tags=[" scan ", "SCAN", "Ưu tiên"]
        )
        response = self.client.patch(self.document_url, json=changes)
        self.assertEqual(response.status_code, 200, response.text)
        document = response.json()
        self.assertEqual(document["project"], "Nhà máy A")
        self.assertEqual(document["drawing_set"], "P&ID 01")
        self.assertEqual(document["tags"], ["scan", "Ưu tiên"])
        self.assertGreater(document["updated_at"], document["created_at"])
        self.change_status("completed").raise_for_status()
        self.client.put(self.base, json=self.body()).raise_for_status()
        fixtures.web.drawings.clear()
        loaded = self.client.get(self.document_url).json()
        self.assertEqual(loaded["tags"], document["tags"])
        self.assertEqual(loaded["project"], document["project"])
        self.assertEqual(loaded["drawing_set"], document["drawing_set"])
        for invalid in (
            {**changes, "project": "a" * 121},
            {**changes, "tags": [""]},
            {**changes, "tags": ["a" * 61]},
            {**changes, "tags": ["a"] * 31},
            {**changes, "width": 1},
        ):
            with self.subTest(invalid=invalid):
                self.assertEqual(
                    self.client.patch(self.document_url, json=invalid).status_code, 422
                )

    def test_existing_annotations_default_to_in_progress_without_inventing_completion(self):
        self.client.put(self.base, json=self.body()).raise_for_status()
        self.storage.documents[self.document["id"]].pop("page_workflows")
        loaded = self.client.get(self.document_url).json()
        self.assertEqual(loaded["page_workflows"]["1"]["status"], "in_progress")
        self.assertEqual(loaded["page_workflows"]["1"]["revision"], 0)
        self.assertEqual(loaded["completed_page_count"], 0)

    def test_drawing_revision_metadata_survives_older_organization_clients(self):
        changes = dict(
            project="Plant A",
            drawing_set="PID",
            tags=[],
            drawing_number="PID-100",
            revision_label="03",
            lifecycle="superseded",
        )
        response = self.client.patch(self.document_url, json=changes)
        self.assertEqual(response.status_code, 200, response.text)
        for key, value in changes.items():
            self.assertEqual(response.json()[key], value)
        response = self.client.patch(
            self.document_url, json=dict(project="Plant A", drawing_set="PID", tags=["updated"])
        )
        self.assertEqual(response.json()["revision_label"], "03")
        self.assertEqual(response.json()["lifecycle"], "superseded")
        self.assertEqual(
            self.client.patch(
                self.document_url, json={**changes, "lifecycle": "invalid"}
            ).status_code,
            422,
        )
