"""PostgreSQL catalog API and one-time SQLite migration checks.

Run with SYMBOL_TEST_DATABASE=1 against a disposable or local PostgreSQL server.
Each test creates and drops its own schema, leaving application tables untouched.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import os
import sqlite3
import sys
import tempfile
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
import psycopg
from fastapi import FastAPI
from PIL import Image
from psycopg import sql

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from app import symbol_library as library


@unittest.skipUnless(
    os.getenv("SYMBOL_TEST_DATABASE") == "1",
    "Set SYMBOL_TEST_DATABASE=1 to run PostgreSQL integration tests",
)
class TestSymbolLibrary(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original = (library.ROOT, library.DB_PATH, library.ASSET_DIR, library.connection)
        self.schema = f"symbol_test_{uuid.uuid4().hex}"
        self.admin = library.connection()
        self.admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
        self.admin.commit()

        def isolated_connection():
            db = self.original[3]()
            db.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(self.schema)))
            db.commit()
            return db

        library.connection = isolated_connection
        library.ROOT = Path(self.temp.name)
        library.DB_PATH = library.ROOT / "symbols.sqlite3"
        library.ASSET_DIR = library.ROOT / "assets"
        app = FastAPI()
        app.include_router(library.router)
        self.app = app

    def tearDown(self):
        library.ROOT, library.DB_PATH, library.ASSET_DIR, library.connection = self.original
        self.admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema)))
        self.admin.commit()
        self.admin.close()
        self.temp.cleanup()

    def request(self, method, path, **kwargs):
        async def send():
            transport = httpx.ASGITransport(app=self.app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://testserver"
            ) as client:
                return await client.request(method, path, **kwargs)

        return asyncio.run(send())

    @staticmethod
    def preview_bytes():
        image = io.BytesIO()
        Image.new("RGB", (24, 24), "white").save(image, "PNG")
        return image.getvalue()

    def test_seed_import_update_delete_and_restart(self):
        library.init_library()
        initial = self.request("GET", "/api/v1/symbol-library")
        self.assertEqual(initial.status_code, 200)
        self.assertEqual({item["code"] for item in initial.json()}, {"CRV-001", "GLV-001"})

        preview = self.preview_bytes()
        files = {
            "source": ("new.dwg", b"example drawing data", "application/acad"),
            "preview": ("new.png", preview, "image/png"),
        }
        data = {"code": "VLV-003", "name": "Test Valve", "category": "Valves"}
        created = self.request("POST", "/api/v1/symbol-library/import", data=data, files=files)
        self.assertEqual(created.status_code, 201)
        self.assertEqual(
            self.request(
                "POST", "/api/v1/symbol-library/import", data=data, files=files
            ).status_code,
            409,
        )
        self.assertEqual(
            self.request("GET", "/api/v1/symbol-library/VLV-003/preview").content, preview
        )
        self.assertEqual(
            self.request("GET", "/api/v1/symbol-library/VLV-003/source").content,
            b"example drawing data",
        )

        changed = self.request(
            "PATCH",
            "/api/v1/symbol-library/VLV-003",
            json={"enabled": False, "name": "Verified Valve"},
        )
        self.assertEqual(changed.status_code, 200)
        self.assertFalse(changed.json()["enabled"])
        self.assertEqual(self.request("DELETE", "/api/v1/symbol-library/VLV-003").status_code, 204)
        self.assertEqual(
            self.request("GET", "/api/v1/symbol-library/VLV-003/preview").status_code, 404
        )
        self.assertEqual(self.request("DELETE", "/api/v1/symbol-library/VLV-003").status_code, 404)
        self.assertEqual(self.request("DELETE", "/api/v1/symbol-library/CRV-001").status_code, 204)
        library.init_library()
        self.assertEqual(
            [item["code"] for item in self.request("GET", "/api/v1/symbol-library").json()],
            ["GLV-001"],
        )
        with library.connection() as db:
            self.assertEqual(
                db.execute("SELECT count(*) AS n FROM symbol_assets").fetchone()["n"], 2
            )

    def test_invalid_preview_is_not_saved(self):
        library.init_library()
        response = self.request(
            "POST",
            "/api/v1/symbol-library/import",
            data={"code": "BAD-001", "name": "Bad", "category": "Valves"},
            files={
                "source": ("bad.dwg", b"dwg", "application/acad"),
                "preview": ("bad.png", b"not an image", "image/png"),
            },
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(len(self.request("GET", "/api/v1/symbol-library").json()), 2)

    def test_source_only_import_preserves_original_and_creates_editor_image(self):
        library.init_library()
        formats = (
            ("png", "PNG"),
            ("jpg", "JPEG"),
            ("jpeg", "JPEG"),
            ("webp", "WEBP"),
            ("bmp", "BMP"),
            ("tif", "TIFF"),
            ("tiff", "TIFF"),
        )
        for extension, image_format in formats:
            with self.subTest(extension=extension):
                source = io.BytesIO()
                image = Image.new("RGBA" if image_format == "PNG" else "RGB", (1024, 256))
                image.save(source, image_format)
                original = source.getvalue()
                code = f"SRC-{extension.upper()}"
                response = self.request(
                    "POST",
                    "/api/v1/symbol-library/import",
                    data={"code": code, "name": "Source-only symbol", "category": "Valves"},
                    files={"source": (f"symbol.{extension}", original, Image.MIME[image_format])},
                )
                self.assertEqual(response.status_code, 201, response.text)
                self.assertEqual(
                    self.request("GET", response.json()["source_url"]).content, original
                )
                preview = self.request("GET", response.json()["preview"])
                self.assertEqual(preview.headers["content-type"], "image/png")
                with Image.open(io.BytesIO(preview.content)) as thumbnail:
                    self.assertEqual(thumbnail.format, "PNG")
                    self.assertEqual(thumbnail.size, (512, 128))
                    if image_format == "PNG":
                        self.assertEqual(thumbnail.getpixel((0, 0))[3], 0)
        library.init_library()
        self.assertEqual(len(self.request("GET", "/api/v1/symbol-library").json()), 9)

    def test_invalid_source_only_import_does_not_save_symbol(self):
        library.init_library()
        jpeg = io.BytesIO()
        Image.new("RGB", (24, 24)).save(jpeg, "JPEG")
        for filename, content in (
            ("bad.png", b"not an image"),
            ("mismatch.png", jpeg.getvalue()),
            ("drawing.dwg", b"dwg"),
        ):
            with self.subTest(filename=filename):
                response = self.request(
                    "POST",
                    "/api/v1/symbol-library/import",
                    data={"code": "BAD-SOURCE", "name": "Invalid source", "category": "Valves"},
                    files={"source": (filename, content, "application/octet-stream")},
                )
                self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(len(self.request("GET", "/api/v1/symbol-library").json()), 2)

    def test_migrates_sqlite_bytes_once_without_reseeding(self):
        library.ASSET_DIR.mkdir(parents=True)
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(library.DB_PATH) as old:
            old.executescript("""
                CREATE TABLE symbol_definitions (
                    code TEXT PRIMARY KEY, name TEXT, category TEXT, enabled INTEGER,
                    origin TEXT, preview_left INTEGER, preview_top INTEGER,
                    preview_width INTEGER, preview_height INTEGER, created_at TEXT, updated_at TEXT
                );
                CREATE TABLE symbol_assets (
                    id INTEGER PRIMARY KEY, symbol_code TEXT, role TEXT, filename TEXT,
                    content_type TEXT, sha256 TEXT, byte_size INTEGER,
                    storage_name TEXT, created_at TEXT
                );
            """)
            old.execute(
                "INSERT INTO symbol_definitions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "LEG-001",
                    "Legacy Valve",
                    "Valves",
                    1,
                    "web-import",
                    None,
                    None,
                    None,
                    None,
                    now,
                    now,
                ),
            )
            for role, filename, data, mime in (
                ("source", "legacy.dwg", b"legacy drawing", "application/acad"),
                ("preview", "legacy.png", self.preview_bytes(), "image/png"),
            ):
                storage_name = f"legacy-{role}{Path(filename).suffix}"
                (library.ASSET_DIR / storage_name).write_bytes(data)
                old.execute(
                    "INSERT INTO symbol_assets (symbol_code, role, filename, content_type, sha256, byte_size, storage_name, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        "LEG-001",
                        role,
                        filename,
                        mime,
                        hashlib.sha256(data).hexdigest(),
                        len(data),
                        storage_name,
                        now,
                    ),
                )

        library.init_library()
        self.assertEqual(
            [item["code"] for item in self.request("GET", "/api/v1/symbol-library").json()],
            ["LEG-001"],
        )
        self.assertEqual(
            self.request("GET", "/api/v1/symbol-library/LEG-001/source").content, b"legacy drawing"
        )
        self.assertEqual(self.request("DELETE", "/api/v1/symbol-library/LEG-001").status_code, 204)
        library.init_library()
        self.assertEqual(self.request("GET", "/api/v1/symbol-library").json(), [])
        self.assertTrue(library.DB_PATH.is_file())
