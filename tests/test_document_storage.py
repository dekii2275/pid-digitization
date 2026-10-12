"""Real PostgreSQL/MinIO checks in a disposable schema and bucket."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from minio.error import S3Error
from psycopg import OperationalError, sql

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from app import document_storage as storage


@unittest.skipUnless(
    os.getenv("DOCUMENT_TEST_STORAGE") == "1", "Set DOCUMENT_TEST_STORAGE=1 for real storage tests"
)
class TestDocumentStorage(unittest.TestCase):
    def setUp(self):
        self.real_connection = storage.connection
        self.schema = "drawing_test_" + uuid.uuid4().hex
        self.bucket = "drawing-test-" + uuid.uuid4().hex
        self.enterContext(patch.dict(os.environ, MINIO_BUCKET=self.bucket))
        self.temporary = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(self.temporary)
        with self.real_connection() as db:
            db.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
        self.addCleanup(self.cleanup_storage)
        self.enterContext(patch.object(storage, "connection", self.connection))
        storage.init_documents(self.root)

    def connection(self):
        db = self.real_connection()
        db.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(self.schema)))
        return db

    def cleanup_storage(self):
        client = storage.client()
        if client.bucket_exists(self.bucket):
            for item in client.list_objects(self.bucket, recursive=True):
                client.remove_object(self.bucket, item.object_name)
            client.remove_bucket(self.bucket)
        with self.real_connection() as db:
            db.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema)))

    def source(self):
        id_ = uuid.uuid4().hex
        source = self.root / f"{id_}.pdf"
        source.write_bytes(b"original drawing bytes")
        metadata = dict(
            extension=".pdf",
            original_name="drawing.pdf",
            source_type="pdf",
            page_count=2,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        return id_, source, metadata

    def test_original_metadata_annotations_and_delete_are_durable(self):
        id_, path, metadata = self.source()
        expected = path.read_bytes()
        saved = storage.save_source(id_, path, metadata)
        path.unlink()
        loaded = storage.get_document(id_)
        self.assertEqual(loaded["object_key"], saved["object_key"])
        self.assertEqual(storage.cache_source(loaded, path).read_bytes(), expected)
        annotation = dict(
            revision=1,
            saved_at=metadata["created_at"],
            symbols=[],
            texts=[dict(id="t1", text="P-101")],
            relations=[],
        )
        storage.save_annotation(id_, 2, annotation, expected_revision=0)
        self.assertEqual(storage.read_annotation(id_, 2), annotation)
        self.assertEqual(storage.list_documents(True)[0]["labeled_pages"], [2])
        self.assertEqual(storage.list_documents(False), [])
        with self.assertRaises(HTTPException) as conflict:
            storage.save_annotation(id_, 2, annotation, expected_revision=0)
        self.assertEqual(conflict.exception.status_code, 409)
        storage.delete_document(id_)
        self.assertIsNone(storage.get_document(id_))
        self.assertIsNone(storage.read_annotation(id_, 2))
        with self.assertRaises(S3Error) as missing:
            storage.client().stat_object(saved["bucket"], saved["object_key"])
        self.assertEqual(missing.exception.code, "NoSuchKey")

    def test_database_failure_removes_uploaded_object(self):
        id_, path, metadata = self.source()
        with patch.object(
            storage, "connection", side_effect=OperationalError("database unavailable")
        ):
            with self.assertRaises(OperationalError):
                storage.save_source(id_, path, metadata)
        self.assertIsNone(storage.get_document(id_))
        self.assertEqual(list(storage.client().list_objects(self.bucket, recursive=True)), [])

    def test_workflow_and_organization_survive_saves_conflicts_restart_and_delete(self):
        id_, path, metadata = self.source()
        storage.save_source(id_, path, metadata)
        storage.update_document(id_, dict(project="Nhà máy A", drawing_set="P&ID", tags=["scan"]))
        for revision, status in enumerate(("in_progress", "pending_review", "completed")):
            storage.save_page_status(id_, 2, status, revision, 0)
        completed = storage.get_document(id_)
        self.assertEqual(completed["completed_page_count"], 1)
        self.assertEqual(completed["annotation_count"], 0)
        with self.assertRaises(HTTPException) as conflict:
            storage.save_page_status(id_, 2, "not_started", 0, 0)
        self.assertEqual(conflict.exception.status_code, 409)
        storage.init_documents(self.root)
        self.assertEqual(storage.get_document(id_), completed)
        annotation = dict(
            revision=1,
            saved_at=datetime.now(timezone.utc).isoformat(),
            symbols=[],
            texts=[],
            relations=[],
        )
        storage.save_annotation(id_, 2, annotation, 0)
        document = storage.get_document(id_)
        self.assertEqual(document["completed_page_count"], 1)
        self.assertEqual(document["page_workflows"]["2"]["status"], "completed")
        workflow = document["page_workflows"]["2"]
        self.assertEqual(workflow["annotation_revision"], 1)
        storage.save_page_status(id_, 2, "completed", workflow["revision"], 1)
        annotation.update(revision=2, saved_at=datetime.now(timezone.utc).isoformat())
        storage.save_annotation(id_, 2, annotation, 1)
        self.assertEqual(storage.get_document(id_)["completed_page_count"], 1)
        with self.assertRaises(HTTPException) as stale:
            storage.save_page_status(id_, 2, "in_progress", workflow["revision"] + 1, 1)
        self.assertEqual(stale.exception.status_code, 409)
        annotation.update(
            revision=3,
            saved_at=datetime.now(timezone.utc).isoformat(),
            texts=[dict(id="t1", text="P-101")],
        )
        storage.save_annotation(id_, 2, annotation, 2)
        document = storage.get_document(id_)
        self.assertEqual(document["completed_page_count"], 0)
        self.assertEqual(document["project"], "Nhà máy A")
        self.assertEqual(document["tags"], ["scan"])
        storage.delete_document(id_)
        self.assertIsNone(storage.get_document(id_))

    def test_old_annotation_metadata_gets_in_progress_summary_and_validates_pages(self):
        id_, path, metadata = self.source()
        storage.save_source(id_, path, metadata)
        annotation = dict(
            revision=1,
            saved_at=datetime.now(timezone.utc).isoformat(),
            symbols=[],
            texts=[],
            relations=[],
        )
        with self.connection() as db:
            from psycopg.types.json import Jsonb

            db.execute(
                "INSERT INTO drawing_annotations VALUES (%s, %s, %s, %s)",
                (id_, 1, Jsonb(annotation), annotation["saved_at"]),
            )
        document = storage.get_document(id_)
        self.assertEqual(document["page_workflows"]["1"]["status"], "in_progress")
        self.assertEqual(document["completed_page_count"], 0)
        for page, status, expected in (
            (0, "completed", 404),
            (3, "completed", 404),
            (1, "unknown", 422),
        ):
            with self.subTest(page=page, status=status):
                with self.assertRaises(HTTPException) as error:
                    storage.save_page_status(id_, page, status, 0, 0)
                self.assertEqual(error.exception.status_code, expected)

    def test_failed_minio_delete_preserves_metadata_and_annotations(self):
        id_, path, metadata = self.source()
        storage.save_source(id_, path, metadata)
        with patch.object(storage, "client") as client:
            client.return_value.remove_object.side_effect = RuntimeError("MinIO unavailable")
            with self.assertRaises(RuntimeError):
                storage.delete_document(id_)
        self.assertIsNotNone(storage.get_document(id_))

    def test_legacy_migration_runs_once_and_does_not_resurrect_deleted_drawing(self):
        id_, path, metadata = self.source()
        (self.root / f"{id_}.json").write_text(json.dumps(metadata), encoding="utf-8")
        with self.connection() as db:
            db.execute("DELETE FROM drawing_storage_migrations")
        storage.init_documents(self.root)
        self.assertEqual(storage.get_document(id_)["original_name"], "drawing.pdf")
        self.assertEqual(path.read_bytes(), b"original drawing bytes")
        storage.delete_document(id_)
        storage.init_documents(self.root)
        self.assertEqual(storage.list_documents(), [])
        self.assertEqual(list(storage.client().list_objects(self.bucket, recursive=True)), [])
