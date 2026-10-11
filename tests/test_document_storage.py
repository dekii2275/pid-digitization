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
