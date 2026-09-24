"""Adapt local symbol/OCR/line JSON into the legacy graph-construction API.

The legacy topology implementation expects normalized coordinates and the
hierarchical symbol labels used by the original Azure service.  The current
local baselines emit pixel-coordinate JSON with flat YOLO class names.  This
module is deliberately an adapter: it reuses the legacy text-to-symbol
correlation service and calls ``construct_graph`` without changing the legacy
topology code.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import types
from pathlib import Path
from typing import Any, Iterable, Sequence

import cv2
import numpy as np


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
LEGACY_SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(LEGACY_SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(LEGACY_SOURCE_ROOT))


def _configure_legacy_runtime() -> None:
    """Allow the local graph module to run without Azure service credentials.

    ``app.config`` validates deployment-only settings at import time.  The
    graph algorithm does not use those services, so local runs get harmless
    placeholders while preserving any values already supplied by the user.
    """

    defaults = {
        "DEBUG": "false",
        "FORM_RECOGNIZER_ENDPOINT": "local://form-recognizer",
        "BLOB_STORAGE_ACCOUNT_URL": "local://blob-storage",
        "BLOB_STORAGE_CONTAINER_NAME": "local",
        "SYMBOL_DETECTION_API": "local://symbol-detection",
        "SYMBOL_DETECTION_API_BEARER_TOKEN": "local",
        "GRAPH_DB_CONNECTION_STRING": "local://graph-db",
    }
    for key, value in defaults.items():
        if not os.environ.get(key):
            os.environ[key] = value
    debug_value = os.environ.get("DEBUG", "").strip().casefold()
    if debug_value in {"1", "true", "yes", "on"}:
        os.environ["DEBUG"] = "true"
    else:
        os.environ["DEBUG"] = "false"

    # The checked-in legacy source uses Pydantic 1 imports while the current
    # local OCR environment may provide Pydantic 2.  Pydantic 2 ships its v1
    # compatibility namespace, so route legacy imports through that namespace
    # without modifying the legacy source files.
    try:
        import pydantic.v1 as pydantic_v1

        sys.modules["pydantic"] = pydantic_v1
    except ImportError:
        pass

    # The graph code only needs ``get_logger``.  Keep local topology runs
    # usable when the optional server-side ECS logging package is absent.
    try:
        import ecs_logging  # noqa: F401
    except ModuleNotFoundError:
        logger_module = types.ModuleType("logger_config")

        def get_logger(logger_name: str) -> logging.Logger:
            logger = logging.getLogger(logger_name)
            if not logger.handlers:
                handler = logging.StreamHandler()
                handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
                logger.addHandler(handler)
            logger.setLevel(logging.INFO)
            return logger

        logger_module.get_logger = get_logger  # type: ignore[attr-defined]
        sys.modules.setdefault("logger_config", logger_module)


_configure_legacy_runtime()

# Importing the legacy ``text_detection`` package eagerly loads its Azure OCR
# client.  The adapter only needs the pure geometry correlation helper, so keep
# that optional service import out of this local execution path.
sys.modules.setdefault(
    "app.services.text_detection.text_detection_service",
    types.ModuleType("app.services.text_detection.text_detection_service"),
)

from app.models.bounding_box import BoundingBox  # noqa: E402
from app.models.graph_construction.graph_construction_request import (  # noqa: E402
    GraphConstructionInferenceRequest,
)
from app.models.graph_construction.graph_construction_response import (  # noqa: E402
    GraphConstructionInferenceResponse,
)
from app.models.image_details import ImageDetails  # noqa: E402
from app.models.line_detection.line_detection_response import (  # noqa: E402
    LineDetectionInferenceResponse,
)
from app.models.line_detection.line_segment import LineSegment  # noqa: E402
from app.models.symbol_detection.label import Label  # noqa: E402
from app.models.symbol_detection.symbol_detection_inference_response import (  # noqa: E402
    SymbolDetectionInferenceResponse,
)
from app.models.text_detection.symbol_and_text_associated import (  # noqa: E402
    SymbolAndTextAssociated,
)
from app.models.text_detection.text_detection_inference_response import (  # noqa: E402
    TextDetectionInferenceResponse,
)
from app.models.text_detection.text_recognized import TextRecognized  # noqa: E402
from app.services.graph_construction.graph_construction_service import (  # noqa: E402
    construct_graph,
)
from app.services.text_detection.symbol_to_text_correlation_service import (  # noqa: E402
    correlate_symbols_with_text,
)


IMAGE_SUFFIXES = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}

VALVE_CLASSES = {
    "welded gate valve",
    "plug valve",
    "globe valve no",
    "gate valve no",
    "ball valve",
    "butterfly valve",
    "manual gate valve",
    "check valve",
    "diaphragm valve",
    "needle valve",
    "sealing gate valve",
    "gate valve nc",
    "globe valve nc",
    "control valve",
    "rotary valve no",
    "rotary valve nc",
    "circle valve",
}

INDICATOR_CLASSES = {
    "field mounted discrete indicator",
    "field mounted discrete recorder",
    "discrete with primary local access",
    "discrete with auxiliary local access",
    "solenoid actuator",
    "shared with primary local access",
    "shared control logic",
}

PIPING_CLASSES = {
    "spade blind",
    "spade close blind (flanged)",
    "spade open blind (flanged)",
    "right concentric reducer",
    "flanged connection",
    "heating coil tubes",
    "jacketed pipe",
    "mid arrow flow direction",
}


class AdapterError(ValueError):
    """Raised when an upstream JSON contract cannot be adapted safely."""


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AdapterError(f"Could not read JSON input: {path}") from exc
    except json.JSONDecodeError as exc:
        raise AdapterError(f"Invalid JSON input: {path}: {exc}") from exc


def _page_payload(document: Any, page_number: int) -> dict[str, Any]:
    """Return one page from either a page-list document or a direct payload."""

    if isinstance(document, dict) and isinstance(document.get("pages"), list):
        for page in document["pages"]:
            if isinstance(page, dict) and int(page.get("page_number", 0)) == page_number:
                return page
        raise AdapterError(f"Page {page_number} is not present in input JSON")
    if isinstance(document, dict):
        return document
    raise AdapterError("Expected a JSON object or a document with a pages list")


def _image_from_source(source: Path) -> tuple[np.ndarray, bytes]:
    """Read a raster source and return its BGR image plus original bytes."""

    if source.suffix.lower() not in IMAGE_SUFFIXES:
        raise AdapterError(
            "topology_adapter currently accepts raster images. For PDF input, "
            "run the page stages first and pass a rendered page image."
        )
    try:
        raw = source.read_bytes()
    except OSError as exc:
        raise AdapterError(f"Could not read source image: {source}") from exc
    image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise AdapterError(f"Could not decode source image: {source}")
    return image, raw


def _normalise_coordinate(value: float, size: int) -> float:
    if size <= 0:
        raise AdapterError("Image dimensions must be positive")
    return max(0.0, min(1.0, float(value) / float(size)))


def _normalise_bbox(
    bbox: Sequence[Any],
    width: int,
    height: int,
) -> tuple[float, float, float, float]:
    if len(bbox) != 4:
        raise AdapterError(f"Bounding box must contain four values: {bbox!r}")
    try:
        x1, y1, x2, y2 = (float(value) for value in bbox)
    except (TypeError, ValueError) as exc:
        raise AdapterError(f"Bounding box contains a non-numeric value: {bbox!r}") from exc
    left, right = sorted((x1, x2))
    top, bottom = sorted((y1, y2))
    left = max(0.0, min(float(width), left))
    right = max(0.0, min(float(width), right))
    top = max(0.0, min(float(height), top))
    bottom = max(0.0, min(float(height), bottom))
    if right <= left or bottom <= top:
        raise AdapterError(f"Bounding box is degenerate: {bbox!r}")
    return (
        _normalise_coordinate(left, width),
        _normalise_coordinate(top, height),
        _normalise_coordinate(right, width),
        _normalise_coordinate(bottom, height),
    )


def _legacy_symbol_label(class_name: str) -> tuple[str, str | None]:
    """Map a flat YOLO class to the legacy hierarchical label namespace."""

    canonical = " ".join(str(class_name).split()).strip()
    lowered = canonical.casefold()
    if lowered in VALVE_CLASSES:
        return f"Instrument/Valve/{canonical}", None
    if lowered in INDICATOR_CLASSES:
        return f"Instrument/Indicator/{canonical}", None
    if lowered in PIPING_CLASSES:
        return f"Piping/Fittings/{canonical}", None
    # Keep unknown classes visible to the legacy graph, but report the fallback
    # because the original service only assigns semantic behavior by prefixes.
    return f"Piping/Fittings/{canonical}", (
        f"No explicit legacy label mapping for YOLO class {canonical!r}; "
        "fell back to Piping/Fittings/."
    )


def _extract_bbox(item: dict[str, Any]) -> Sequence[Any]:
    bbox = item.get("bbox")
    if not isinstance(bbox, (list, tuple)):
        raise AdapterError(f"Input item has no bbox: {item!r}")
    return bbox


def _build_symbols(
    payload: dict[str, Any],
    width: int,
    height: int,
) -> tuple[SymbolDetectionInferenceResponse, list[str], int]:
    detections = payload.get("detections", [])
    if not isinstance(detections, list):
        raise AdapterError("Symbol JSON field 'detections' must be a list")

    labels: list[Label] = []
    mapping_warnings: list[str] = []
    skipped = 0
    for index, item in enumerate(detections):
        if not isinstance(item, dict):
            skipped += 1
            continue
        class_name = str(item.get("class_name", "")).strip()
        if not class_name:
            skipped += 1
            continue
        try:
            top_x, top_y, bottom_x, bottom_y = _normalise_bbox(
                _extract_bbox(item), width, height
            )
        except AdapterError:
            skipped += 1
            continue
        label, warning = _legacy_symbol_label(class_name)
        if warning:
            mapping_warnings.append(warning)
        score = item.get("confidence")
        try:
            score = float(score) if score is not None else None
        except (TypeError, ValueError):
            score = None
        labels.append(
            Label(
                topX=top_x,
                topY=top_y,
                bottomX=bottom_x,
                bottomY=bottom_y,
                id=index,
                label=label,
                score=score,
            )
        )

    result = SymbolDetectionInferenceResponse(
        image_url=str(payload.get("source", "local-symbol-detections")),
        image_details=ImageDetails(format="png", width=width, height=height),
        bounding_box_inclusive=BoundingBox(topX=0.0, topY=0.0, bottomX=1.0, bottomY=1.0),
        label=labels,
    )
    return result, sorted(set(mapping_warnings)), skipped


def _build_texts(
    payload: dict[str, Any],
    width: int,
    height: int,
) -> tuple[list[TextRecognized], int]:
    texts = payload.get("texts", [])
    if not isinstance(texts, list):
        raise AdapterError("OCR JSON field 'texts' must be a list")

    output: list[TextRecognized] = []
    skipped = 0
    for item in texts:
        if not isinstance(item, dict):
            skipped += 1
            continue
        text = " ".join(str(item.get("text", "")).split()).strip()
        if not text:
            skipped += 1
            continue
        try:
            top_x, top_y, bottom_x, bottom_y = _normalise_bbox(
                _extract_bbox(item), width, height
            )
        except AdapterError:
            skipped += 1
            continue
        output.append(
            TextRecognized(
                text=text,
                topX=top_x,
                topY=top_y,
                bottomX=bottom_x,
                bottomY=bottom_y,
            )
        )
    return output, skipped


def _line_items(payload: dict[str, Any]) -> Iterable[dict[str, Any]]:
    lines = payload.get("lines", [])
    if not isinstance(lines, list):
        raise AdapterError("Line JSON field 'lines' must be a list")
    for item in lines:
        if isinstance(item, dict):
            yield item


def _line_point(item: dict[str, Any], key: str) -> Sequence[Any]:
    point = item.get(key)
    if isinstance(point, (list, tuple)) and len(point) == 2:
        return point
    legacy_key = "start" if key == "start" else "end"
    x_key = "startX" if legacy_key == "start" else "endX"
    y_key = "startY" if legacy_key == "start" else "endY"
    if x_key in item and y_key in item:
        return item[x_key], item[y_key]
    raise AdapterError(f"Line item has no {key} point: {item!r}")


def _looks_normalised(line_items: Sequence[dict[str, Any]]) -> bool:
    values: list[float] = []
    for item in line_items:
        for key in ("start", "end"):
            try:
                values.extend(float(value) for value in _line_point(item, key))
            except (TypeError, ValueError, AdapterError):
                continue
    return bool(values) and max(abs(value) for value in values) <= 1.5


def _build_lines(
    payload: dict[str, Any],
    width: int,
    height: int,
) -> tuple[LineDetectionInferenceResponse, str, int]:
    items = list(_line_items(payload))
    coordinate_mode = "normalized" if _looks_normalised(items) else "pixels"
    output: list[LineSegment] = []
    skipped = 0
    for item in items:
        try:
            start = _line_point(item, "start")
            end = _line_point(item, "end")
            if coordinate_mode == "normalized":
                start_x, start_y, end_x, end_y = (
                    max(0.0, min(1.0, float(start[0]))),
                    max(0.0, min(1.0, float(start[1]))),
                    max(0.0, min(1.0, float(end[0]))),
                    max(0.0, min(1.0, float(end[1]))),
                )
            else:
                start_x = _normalise_coordinate(float(start[0]), width)
                start_y = _normalise_coordinate(float(start[1]), height)
                end_x = _normalise_coordinate(float(end[0]), width)
                end_y = _normalise_coordinate(float(end[1]), height)
            if start_x == end_x and start_y == end_y:
                skipped += 1
                continue
        except (TypeError, ValueError, AdapterError):
            skipped += 1
            continue
        output.append(
            LineSegment(startX=start_x, startY=start_y, endX=end_x, endY=end_y)
        )

    result = LineDetectionInferenceResponse(
        image_url=str(payload.get("source", "local-line-detections")),
        image_details=ImageDetails(format="png", width=width, height=height),
        line_segments_count=len(output),
        line_segments=output,
    )
    return result, coordinate_mode, skipped


def _build_text_detection_request(
    source: Path,
    image_details: ImageDetails,
    all_text: list[TextRecognized],
    associated: list[SymbolAndTextAssociated],
    propagation_pass_exhaustive_search: bool,
) -> GraphConstructionInferenceRequest:
    return GraphConstructionInferenceRequest(
        image_url=str(source.resolve()),
        image_details=image_details,
        bounding_box_inclusive=BoundingBox(
            topX=0.0,
            topY=0.0,
            bottomX=1.0,
            bottomY=1.0,
        ),
        all_text_list=all_text,
        text_and_symbols_associated_list=associated,
        hough_threshold=None,
        hough_min_line_length=None,
        hough_max_line_gap=None,
        hough_rho=None,
        hough_theta=None,
        thinning_enabled=None,
        propagation_pass_exhaustive_search=propagation_pass_exhaustive_search,
    )


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run_adapter(
    source: Path,
    symbols_path: Path,
    texts_path: Path,
    lines_path: Path,
    output_dir: Path,
    page_number: int = 1,
    association_area_threshold: float = 0.8,
    association_distance_threshold: float = 0.01,
    symbol_label_prefixes_with_text: Sequence[str] = (
        "Instrument/",
        "Equipment/",
        "Piping/Endpoint/Pagination",
    ),
    propagation_pass_exhaustive_search: bool = False,
) -> dict[str, Any]:
    """Adapt upstream contracts, run legacy topology, and write all outputs."""

    image, image_bytes = _image_from_source(source)
    height, width = image.shape[:2]
    symbols_payload = _page_payload(_load_json(symbols_path), page_number)
    texts_payload = _page_payload(_load_json(texts_path), page_number)
    lines_payload = _page_payload(_load_json(lines_path), page_number)

    symbols, mapping_warnings, skipped_symbols = _build_symbols(symbols_payload, width, height)
    all_text, skipped_text = _build_texts(texts_payload, width, height)
    lines, line_coordinate_mode, skipped_lines = _build_lines(lines_payload, width, height)

    prefixes = tuple(prefix.casefold() for prefix in symbol_label_prefixes_with_text)
    associated = correlate_symbols_with_text(
        all_text,
        symbols,
        association_area_threshold,
        association_distance_threshold,
        prefixes,
    )
    text_request = _build_text_detection_request(
        source,
        symbols.image_details,
        all_text,
        associated,
        propagation_pass_exhaustive_search,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    graph_image_path = output_dir / "graph_network.png"
    connections_image_path = output_dir / "graph_connections_overlay.png"
    lines_symbols_image_path = output_dir / "graph_lines_symbols.png"
    connectivity_path = output_dir / "connectivity.json"
    report_path = output_dir / "adapter_report.json"

    asset_connectivities, arrow_nodes = construct_graph(
        pid_id=source.stem,
        pid_image=image_bytes,
        text_detection_results=text_request,
        line_detection_results=lines,
        output_image_graph_path=str(graph_image_path),
        debug_image_graph_connections_path=str(connections_image_path),
        debug_image_graph_with_lines_and_symbols_path=str(lines_symbols_image_path),
        symbol_label_prefixes_to_include_in_graph_image_output={
            "Instrument/",
            "Equipment/",
            "Piping/Endpoint/Pagination",
        },
    )

    response = GraphConstructionInferenceResponse(
        image_url=str(graph_image_path.resolve()),
        image_details=ImageDetails(format="png", width=width, height=height),
        connected_symbols=asset_connectivities,
    )
    _write_json(connectivity_path, response.dict())

    associated_with_text = sum(
        1 for symbol in associated if symbol.text_associated not in (None, "")
    )
    report = {
        "source": str(source.resolve()),
        "page_number": page_number,
        "image_size": {"width": width, "height": height},
        "inputs": {
            "symbols": str(symbols_path.resolve()),
            "texts": str(texts_path.resolve()),
            "lines": str(lines_path.resolve()),
        },
        "counts": {
            "symbol_detections": len(symbols.label),
            "symbols_skipped": skipped_symbols,
            "ocr_texts": len(all_text),
            "texts_skipped": skipped_text,
            "symbols_with_associated_text": associated_with_text,
            "line_segments": len(lines.line_segments),
            "lines_skipped": skipped_lines,
            "connected_assets": len(asset_connectivities),
            "arrow_nodes": len(arrow_nodes),
        },
        "coordinate_conversion": {
            "symbol_bbox": "pixel xyxy -> legacy normalized topX/topY/bottomX/bottomY",
            "ocr_bbox": "pixel xyxy -> legacy normalized topX/topY/bottomX/bottomY",
            "line_points": line_coordinate_mode,
        },
        "legacy_assumptions": [
            "The legacy graph module consumes normalized coordinates in [0, 1].",
            "The full page is used as bounding_box_inclusive because local baselines do not emit a legacy content box.",
            "OCR-to-symbol association reuses the legacy correlation service with the configured area and distance thresholds.",
            "Only symbols with the legacy text-bearing prefixes and valid alpha-numeric associated text become output assets.",
            "The line baseline is geometric only; it does not classify process versus signal lines before legacy construction.",
        ],
        "label_mapping_warnings": mapping_warnings,
        "outputs": {
            "connectivity_json": str(connectivity_path.resolve()),
            "graph_network": str(graph_image_path.resolve()),
            "graph_connections_overlay": str(connections_image_path.resolve()),
            "graph_lines_symbols": str(lines_symbols_image_path.resolve()),
            "adapter_report": str(report_path.resolve()),
        },
    }
    _write_json(report_path, report)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--symbols", required=True, type=Path)
    parser.add_argument("--texts", required=True, type=Path)
    parser.add_argument("--lines", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--page-number", type=int, default=1)
    parser.add_argument("--association-area-threshold", type=float, default=0.8)
    parser.add_argument("--association-distance-threshold", type=float, default=0.01)
    parser.add_argument(
        "--symbol-label-prefixes-with-text",
        default="Instrument/,Equipment/,Piping/Endpoint/Pagination",
    )
    parser.add_argument("--propagation-pass-exhaustive-search", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    for path in (args.source, args.symbols, args.texts, args.lines):
        if not path.is_file():
            raise FileNotFoundError(path)
    prefixes = tuple(
        item.strip()
        for item in args.symbol_label_prefixes_with_text.split(",")
        if item.strip()
    )
    report = run_adapter(
        source=args.source,
        symbols_path=args.symbols,
        texts_path=args.texts,
        lines_path=args.lines,
        output_dir=args.output_dir,
        page_number=args.page_number,
        association_area_threshold=args.association_area_threshold,
        association_distance_threshold=args.association_distance_threshold,
        symbol_label_prefixes_with_text=prefixes,
        propagation_pass_exhaustive_search=args.propagation_pass_exhaustive_search,
    )
    print(
        "Topology complete: "
        f"assets={report['counts']['connected_assets']}, "
        f"lines={report['counts']['line_segments']}"
    )
    print(f"Connectivity JSON: {report['outputs']['connectivity_json']}")
    print(f"Debug overlay: {report['outputs']['graph_connections_overlay']}")
    print(f"Adapter report: {report['outputs']['adapter_report']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
