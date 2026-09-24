"""Standalone M0 Baseline & Invariant Test Runner (using standard library unittest).

Freezes and validates the baseline outputs of the P&ID digitization pipeline on 4.jpg:
  1. Symbol Detection Invariants:
     - symbols > 0 (1208 detections)
     - confidence in [0.0, 1.0]
     - bboxes within image bounds [7168, 4561]
  2. OCR Invariants:
     - ocr texts > 0 (785 texts)
     - non-empty text strings
     - bboxes within image bounds
  3. Line Detection Invariants:
     - lines > 0 (217 lines)
     - endpoints within image bounds
     - valid orientation: horizontal, vertical, diagonal
     - line length > 0
  4. Topology Invariants:
     - connected_assets > 0 (271 assets)
     - normalized bboxes in [0.0, 1.0]
     - valid image dimensions in connectivity.json
  5. Editor Scene Invariants:
     - scene dimensions match source image [7168, 4561]
     - scene objects > 0 with layers: symbol, text, line
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = REPO_ROOT.parent
FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "baseline_4_snapshot.json"
ARTIFACTS_DIR = REPO_ROOT / "artifacts" / "pid-pipeline" / "4"


class TestM0PipelineInvariants(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not FIXTURE_PATH.is_file():
            raise FileNotFoundError(f"Fixture not found: {FIXTURE_PATH}")
        with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
            cls.snapshot = json.load(f)

        symbols_file = ARTIFACTS_DIR / "symbols" / "detections.json"
        ocr_file = ARTIFACTS_DIR / "ocr" / "ocr.json"
        lines_file = ARTIFACTS_DIR / "lines" / "lines.json"
        connectivity_file = ARTIFACTS_DIR / "topology" / "connectivity.json"
        report_file = ARTIFACTS_DIR / "topology" / "adapter_report.json"
        scene_file = ARTIFACTS_DIR / "editor" / "scene.json"

        for p in [symbols_file, ocr_file, lines_file, connectivity_file, report_file, scene_file]:
            if not p.is_file():
                raise FileNotFoundError(f"Required artifact missing: {p}")

        with open(symbols_file, "r", encoding="utf-8") as f:
            cls.symbols_data = json.load(f)
        with open(ocr_file, "r", encoding="utf-8") as f:
            cls.ocr_data = json.load(f)
        with open(lines_file, "r", encoding="utf-8") as f:
            cls.lines_data = json.load(f)
        with open(connectivity_file, "r", encoding="utf-8") as f:
            cls.connectivity = json.load(f)
        with open(report_file, "r", encoding="utf-8") as f:
            cls.report = json.load(f)
        with open(scene_file, "r", encoding="utf-8") as f:
            cls.scene = json.load(f)

        cls.width = cls.snapshot["image_size"]["width"]
        cls.height = cls.snapshot["image_size"]["height"]

    def test_01_fixture_and_image(self):
        source_rel = self.snapshot["source_image"]
        source_path = WORKSPACE_ROOT / source_rel
        self.assertTrue(source_path.is_file(), f"Source image missing: {source_path}")
        self.assertEqual(self.width, 7168)
        self.assertEqual(self.height, 4561)

    def test_02_symbols_invariants(self):
        pages = self.symbols_data.get("pages", [])
        self.assertGreaterEqual(len(pages), 1)

        detections = pages[0].get("detections", [])
        self.assertGreater(len(detections), 0, "Invariant violated: symbols count == 0")
        self.assertGreaterEqual(len(detections), 1000, f"Expected ~1208 detections, got {len(detections)}")

        for det in detections:
            self.assertIn("class_name", det)
            self.assertTrue(len(det["class_name"]) > 0)

            conf = det.get("confidence", 0.0)
            self.assertTrue(0.0 <= conf <= 1.0, f"Confidence {conf} out of range [0, 1]")

            bbox = det.get("bbox", [])
            self.assertEqual(len(bbox), 4)
            x1, y1, x2, y2 = bbox

            self.assertLessEqual(x1, x2)
            self.assertLessEqual(y1, y2)
            self.assertTrue(0 <= x1 <= self.width and 0 <= x2 <= self.width, f"x out of bounds: {bbox}")
            self.assertTrue(0 <= y1 <= self.height and 0 <= y2 <= self.height, f"y out of bounds: {bbox}")

    def test_03_ocr_invariants(self):
        pages = self.ocr_data.get("pages", [])
        self.assertGreaterEqual(len(pages), 1)

        texts = pages[0].get("texts", [])
        self.assertGreater(len(texts), 0, "Invariant violated: ocr count == 0")
        self.assertGreaterEqual(len(texts), 500, f"Expected ~785 texts, got {len(texts)}")

        for item in texts:
            self.assertIn("text", item)
            self.assertTrue(len(item["text"]) > 0, "OCR text must not be empty")

            conf = item.get("confidence", 0.0)
            self.assertTrue(0.0 <= conf <= 1.0, f"Confidence {conf} out of range [0, 1]")

            bbox = item.get("bbox", [])
            self.assertEqual(len(bbox), 4)
            x1, y1, x2, y2 = bbox

            self.assertLessEqual(x1, x2)
            self.assertLessEqual(y1, y2)
            self.assertTrue(0 <= x1 <= self.width and 0 <= x2 <= self.width, f"x out of bounds: {bbox}")
            self.assertTrue(0 <= y1 <= self.height and 0 <= y2 <= self.height, f"y out of bounds: {bbox}")

    def test_04_lines_invariants(self):
        lines = self.lines_data.get("lines", [])
        self.assertGreater(len(lines), 0, "Invariant violated: lines count == 0")
        self.assertGreaterEqual(len(lines), 150, f"Expected ~217 lines, got {len(lines)}")

        for line in lines:
            start = line.get("start", [])
            end = line.get("end", [])
            self.assertEqual(len(start), 2)
            self.assertEqual(len(end), 2)

            sx, sy = start
            ex, ey = end

            self.assertTrue(0 <= sx <= self.width and 0 <= ex <= self.width)
            self.assertTrue(0 <= sy <= self.height and 0 <= ey <= self.height)

            length = ((ex - sx) ** 2 + (ey - sy) ** 2) ** 0.5
            self.assertGreater(length, 0, f"Line length must be positive: {line}")
            self.assertIn(line.get("orientation"), {"horizontal", "vertical", "diagonal"})

    def test_05_topology_invariants(self):
        counts = self.report.get("counts", {})
        self.assertGreater(counts.get("symbol_detections", 0), 0)
        self.assertGreater(counts.get("ocr_texts", 0), 0)
        self.assertGreater(counts.get("line_segments", 0), 0)
        self.assertGreater(counts.get("connected_assets", 0), 0, "Invariant violated: connected_assets == 0")

        details = self.connectivity.get("image_details", {})
        self.assertEqual(details.get("width"), self.width)
        self.assertEqual(details.get("height"), self.height)

        connected_symbols = self.connectivity.get("connected_symbols", [])
        self.assertGreater(len(connected_symbols), 0, "Invariant violated: connected_symbols == 0")

        for symbol in connected_symbols:
            self.assertIn("id", symbol)
            self.assertIn("label", symbol)
            bbox = symbol.get("bounding_box", {})
            self.assertTrue(0.0 <= bbox.get("topX", 0) <= bbox.get("bottomX", 1) <= 1.0)
            self.assertTrue(0.0 <= bbox.get("topY", 0) <= bbox.get("bottomY", 1) <= 1.0)

    def test_06_editor_scene_invariants(self):
        source_meta = self.scene.get("source", {})
        self.assertEqual(source_meta.get("width"), self.width)
        self.assertEqual(source_meta.get("height"), self.height)

        symbols = self.scene.get("symbols", [])
        texts = self.scene.get("texts", [])
        lines = self.scene.get("lines", [])

        self.assertGreater(len(symbols), 0, "Editor symbols must be > 0")
        self.assertGreater(len(texts), 0, "Editor texts must be > 0")
        self.assertGreater(len(lines), 0, "Editor lines must be > 0")


if __name__ == "__main__":
    runner = unittest.TextTestRunner(verbosity=2)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestM0PipelineInvariants)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
