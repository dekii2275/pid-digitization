"""Baseline invariant & regression tests for the P&ID pipeline (Milestone M0).

These tests freeze the current behavior of the pipeline against the reference
run on 4.jpg, checking structural invariants:
  - symbols > 0, confidence in [0, 1], bbox within image dimensions
  - ocr > 0, confidence in [0, 1], bbox within image dimensions, non-empty text
  - lines > 0, valid endpoints within image dimensions, length > 0
  - topology > 0, valid normalized coordinates, consistent report counts
  - editor scene > 0, valid canvas dimensions and layered objects
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = REPO_ROOT.parent
FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "baseline_4_snapshot.json"
ARTIFACTS_DIR = REPO_ROOT / "artifacts" / "pid-pipeline" / "4"


@pytest.fixture(scope="module")
def baseline_snapshot() -> dict:
    assert FIXTURE_PATH.is_file(), f"Baseline fixture missing: {FIXTURE_PATH}"
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def symbols_data() -> dict:
    symbols_file = ARTIFACTS_DIR / "symbols" / "detections.json"
    assert symbols_file.is_file(), f"Symbols file missing: {symbols_file}"
    with open(symbols_file, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def ocr_data() -> dict:
    ocr_file = ARTIFACTS_DIR / "ocr" / "ocr.json"
    assert ocr_file.is_file(), f"OCR file missing: {ocr_file}"
    with open(ocr_file, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def lines_data() -> dict:
    lines_file = ARTIFACTS_DIR / "lines" / "lines.json"
    assert lines_file.is_file(), f"Lines file missing: {lines_file}"
    with open(lines_file, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def topology_data() -> tuple[dict, dict]:
    connectivity_file = ARTIFACTS_DIR / "topology" / "connectivity.json"
    report_file = ARTIFACTS_DIR / "topology" / "adapter_report.json"
    assert connectivity_file.is_file(), f"Connectivity file missing: {connectivity_file}"
    assert report_file.is_file(), f"Adapter report missing: {report_file}"
    with open(connectivity_file, "r", encoding="utf-8") as f:
        connectivity = json.load(f)
    with open(report_file, "r", encoding="utf-8") as f:
        report = json.load(f)
    return connectivity, report


@pytest.fixture(scope="module")
def editor_scene_data() -> dict:
    scene_file = ARTIFACTS_DIR / "editor" / "scene.json"
    assert scene_file.is_file(), f"Scene file missing: {scene_file}"
    with open(scene_file, "r", encoding="utf-8") as f:
        return json.load(f)


def test_baseline_fixture_and_image_exist(baseline_snapshot):
    source_rel = baseline_snapshot["source_image"]
    source_path = WORKSPACE_ROOT / source_rel
    assert source_path.is_file(), f"Source image does not exist: {source_path}"
    assert baseline_snapshot["image_size"]["width"] == 7168
    assert baseline_snapshot["image_size"]["height"] == 4561


def test_symbols_invariants(symbols_data, baseline_snapshot):
    width = baseline_snapshot["image_size"]["width"]
    height = baseline_snapshot["image_size"]["height"]

    pages = symbols_data.get("pages", [])
    assert len(pages) >= 1, "At least one page must exist in symbols output"

    detections = pages[0].get("detections", [])
    # Invariant: symbols count > 0
    assert len(detections) > 0, "Symbols count must be greater than 0"
    assert len(detections) >= 1000, f"Expected ~1208 detections, got {len(detections)}"

    for det in detections:
        assert "class_name" in det and isinstance(det["class_name"], str)
        assert len(det["class_name"]) > 0

        conf = det.get("confidence", 0.0)
        assert 0.0 <= conf <= 1.0, f"Confidence {conf} out of [0, 1]"

        bbox = det.get("bbox", [])
        assert len(bbox) == 4, f"BBox must have 4 coordinates: {bbox}"
        x1, y1, x2, y2 = bbox

        assert x1 <= x2, f"Invalid bbox x ordering: {bbox}"
        assert y1 <= y2, f"Invalid bbox y ordering: {bbox}"
        # Invariant: within image bounds
        assert 0 <= x1 <= width and 0 <= x2 <= width, f"BBox x out of bounds: {bbox}"
        assert 0 <= y1 <= height and 0 <= y2 <= height, f"BBox y out of bounds: {bbox}"


def test_ocr_invariants(ocr_data, baseline_snapshot):
    width = baseline_snapshot["image_size"]["width"]
    height = baseline_snapshot["image_size"]["height"]

    pages = ocr_data.get("pages", [])
    assert len(pages) >= 1, "At least one page must exist in OCR output"

    texts = pages[0].get("texts", [])
    # Invariant: ocr count > 0
    assert len(texts) > 0, "OCR text count must be greater than 0"
    assert len(texts) >= 500, f"Expected ~785 text items, got {len(texts)}"

    for item in texts:
        assert "text" in item and isinstance(item["text"], str)
        assert len(item["text"]) > 0, "Text must not be empty"

        conf = item.get("confidence", 0.0)
        assert 0.0 <= conf <= 1.0, f"Confidence {conf} out of [0, 1]"

        bbox = item.get("bbox", [])
        assert len(bbox) == 4, f"BBox must have 4 coordinates: {bbox}"
        x1, y1, x2, y2 = bbox

        assert x1 <= x2, f"Invalid OCR bbox x ordering: {bbox}"
        assert y1 <= y2, f"Invalid OCR bbox y ordering: {bbox}"
        assert 0 <= x1 <= width and 0 <= x2 <= width, f"OCR x out of bounds: {bbox}"
        assert 0 <= y1 <= height and 0 <= y2 <= height, f"OCR y out of bounds: {bbox}"


def test_lines_invariants(lines_data, baseline_snapshot):
    width = baseline_snapshot["image_size"]["width"]
    height = baseline_snapshot["image_size"]["height"]

    lines = lines_data.get("lines", [])
    # Invariant: line count > 0
    assert len(lines) > 0, "Lines count must be greater than 0"
    assert len(lines) >= 150, f"Expected ~217 lines, got {len(lines)}"

    for line in lines:
        start = line.get("start", [])
        end = line.get("end", [])
        assert len(start) == 2 and len(end) == 2, f"Line endpoints invalid: {line}"

        sx, sy = start
        ex, ey = end

        assert 0 <= sx <= width and 0 <= ex <= width, f"Line x out of bounds: {line}"
        assert 0 <= sy <= height and 0 <= ey <= height, f"Line y out of bounds: {line}"

        length = ((ex - sx) ** 2 + (ey - sy) ** 2) ** 0.5
        assert length > 0, f"Line length must be positive: {line}"

        assert line.get("orientation") in {"horizontal", "vertical", "diagonal"}


def test_topology_invariants(topology_data, baseline_snapshot):
    connectivity, report = topology_data

    # Report checks
    counts = report.get("counts", {})
    assert counts.get("symbol_detections", 0) > 0
    assert counts.get("ocr_texts", 0) > 0
    assert counts.get("line_segments", 0) > 0
    # Invariant: connected_assets > 0
    assert counts.get("connected_assets", 0) > 0

    # Connectivity checks
    details = connectivity.get("image_details", {})
    assert details.get("width") == baseline_snapshot["image_size"]["width"]
    assert details.get("height") == baseline_snapshot["image_size"]["height"]

    connected_symbols = connectivity.get("connected_symbols", [])
    assert len(connected_symbols) > 0, "Connected symbols must be > 0"

    for symbol in connected_symbols:
        assert "id" in symbol
        assert "label" in symbol
        bbox = symbol.get("bounding_box", {})
        # Invariant: normalized bounding box in [0, 1]
        assert 0.0 <= bbox.get("topX", 0) <= bbox.get("bottomX", 1) <= 1.0
        assert 0.0 <= bbox.get("topY", 0) <= bbox.get("bottomY", 1) <= 1.0


def test_editor_scene_invariants(editor_scene_data, baseline_snapshot):
    width = baseline_snapshot["image_size"]["width"]
    height = baseline_snapshot["image_size"]["height"]

    source_meta = editor_scene_data.get("source", {})
    assert source_meta.get("width") == width
    assert source_meta.get("height") == height

    symbols = editor_scene_data.get("symbols", [])
    texts = editor_scene_data.get("texts", [])
    lines = editor_scene_data.get("lines", [])

    assert len(symbols) > 0, "Editor scene symbols must be > 0"
    assert len(texts) > 0, "Editor scene texts must be > 0"
    assert len(lines) > 0, "Editor scene lines must be > 0"
