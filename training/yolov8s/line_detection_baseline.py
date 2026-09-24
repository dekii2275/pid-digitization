"""Local baseline for detecting P&ID line segments after symbols and OCR.

The detector consumes the global pixel-coordinate contracts emitted by
``tiled_inference.py`` and ``ocr_baseline.py``.  It intentionally does not
crop the page: the source image, masks, skeleton, overlay, and JSON all use
the same coordinate system.

Pipeline::

    source image -> symbol/text mask -> grayscale/binary -> thinning
    -> horizontal/vertical traversal -> diagonal HoughLinesP
    -> direction-aware merge/length filtering -> JSON + overlay

This is a baseline, not a topology or piping/signal-line classifier.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import cv2
import numpy as np

from ocr_baseline import clip_bbox
from tiled_inference import iter_input_pages


IMAGE_SUFFIXES = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_ROOT = REPOSITORY_ROOT / "artifacts" / "line-detection"

BBox = tuple[float, float, float, float]


@dataclass
class Segment:
    """A line segment in global source-image pixel coordinates."""

    x1: float
    y1: float
    x2: float
    y2: float
    orientation: str

    @property
    def length(self) -> float:
        return math.hypot(self.x2 - self.x1, self.y2 - self.y1)

    @property
    def angle(self) -> float:
        return math.degrees(math.atan2(self.y2 - self.y1, self.x2 - self.x1)) % 180.0


@dataclass(frozen=True)
class PageResult:
    page_number: int
    image_size: tuple[int, int]
    lines: tuple[dict[str, Any], ...]
    overlay_name: str
    masked_name: str
    binary_name: str
    thinned_name: str
    symbol_count: int
    text_count: int
    binary_threshold_used: int
    thinning_method: str


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="Original P&ID image or PDF.")
    parser.add_argument(
        "--symbols",
        type=Path,
        default=None,
        help="Global symbol detections JSON, normally tiled-inference/.../detections.json.",
    )
    parser.add_argument(
        "--texts",
        type=Path,
        default=None,
        help="Global OCR JSON, normally ocr-baseline/.../ocr.json.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory. Defaults to artifacts/line-detection/<source-stem>.",
    )
    parser.add_argument("--dpi", type=int, default=600, help="PDF render DPI.")
    parser.add_argument(
        "--pages",
        default="all",
        help="PDF pages to process, for example all, 1, or 1,3-5. Ignored for images.",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=20,
        help="Hough accumulator threshold for diagonal lines.",
    )
    parser.add_argument(
        "--binary-threshold",
        type=int,
        default=0,
        help="Grayscale threshold. 0 uses Otsu; otherwise use a fixed 1-254 value.",
    )
    parser.add_argument("--min-line-length", type=float, default=30.0)
    parser.add_argument(
        "--merge-gap",
        type=float,
        default=12.0,
        help="Maximum pixel gap to bridge while traversing/merging segments.",
    )
    parser.add_argument(
        "--angle-tolerance",
        type=float,
        default=8.0,
        help="Degrees around 0/90 treated as horizontal/vertical and excluded from diagonal Hough output.",
    )
    parser.add_argument(
        "--merge-distance",
        type=float,
        default=2.0,
        help="Maximum perpendicular distance for merging near-collinear segments.",
    )
    parser.add_argument("--hough-rho", type=float, default=1.0)
    parser.add_argument("--hough-theta-degrees", type=float, default=1.0)
    parser.add_argument(
        "--thinning",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Apply Zhang-Suen thinning (default: enabled).",
    )
    return parser


def validate_args(args: argparse.Namespace) -> None:
    if not args.source.is_file():
        raise FileNotFoundError(f"Source not found: {args.source}")
    if args.source.suffix.lower() != ".pdf" and args.source.suffix.lower() not in IMAGE_SUFFIXES:
        raise ValueError(f"Unsupported source type: {args.source.suffix}")
    for path, label in ((args.symbols, "symbols"), (args.texts, "texts")):
        if path is not None and not path.is_file():
            raise FileNotFoundError(f"{label} JSON not found: {path}")
    if args.dpi <= 0:
        raise ValueError("dpi must be positive")
    if not 0 <= args.binary_threshold <= 254:
        raise ValueError("binary-threshold must be 0 (Otsu) or in [1, 254]")
    if args.threshold <= 0 or args.min_line_length <= 0 or args.merge_gap < 0:
        raise ValueError("threshold and min-line-length must be positive; merge-gap must be non-negative")
    if not 0 < args.angle_tolerance < 45:
        raise ValueError("angle-tolerance must be in (0, 45)")
    if args.merge_distance < 0 or args.hough_rho <= 0 or args.hough_theta_degrees <= 0:
        raise ValueError("merge-distance, hough-rho, and hough-theta-degrees must be positive or zero as applicable")


def _page_payload(document: Any, page_number: int) -> Any:
    """Return a page-shaped payload from either a multi-page or direct JSON file."""

    if isinstance(document, dict) and isinstance(document.get("pages"), list):
        for page in document["pages"]:
            if isinstance(page, dict) and int(page.get("page_number", 0)) == page_number:
                return page
        return {}
    return document


def _load_json(path: Path | None) -> Any:
    if path is None:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_boxes(document: Any, page_number: int, key: str) -> list[BBox]:
    """Read xyxy bboxes from the existing symbol/OCR JSON contracts."""

    if document is None:
        return []
    payload = _page_payload(document, page_number)
    if isinstance(payload, dict):
        values = payload.get(key, [])
    elif isinstance(payload, list):
        values = payload
    else:
        values = []

    boxes: list[BBox] = []
    for item in values:
        if not isinstance(item, dict):
            continue
        raw = item.get("bbox")
        if not isinstance(raw, (list, tuple)) or len(raw) != 4:
            continue
        try:
            box = tuple(float(value) for value in raw)
        except (TypeError, ValueError):
            continue
        if box[2] > box[0] and box[3] > box[1]:
            boxes.append(box)  # type: ignore[arg-type]
    return boxes


def _clip_bbox(box: BBox, width: int, height: int) -> tuple[int, int, int, int] | None:
    clipped = clip_bbox(box, width, height)
    if clipped is None:
        return None
    x1 = max(0, min(width, math.floor(clipped[0])))
    y1 = max(0, min(height, math.floor(clipped[1])))
    x2 = max(0, min(width, math.ceil(clipped[2])))
    y2 = max(0, min(height, math.ceil(clipped[3])))
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def mask_regions(
    image: np.ndarray,
    symbol_boxes: Sequence[BBox],
    text_boxes: Sequence[BBox],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Mask symbols/text with the page background and return debug masks."""

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape
    # Border mode is more stable than assuming a pure white scan background.
    border = np.concatenate((gray[0, :], gray[-1, :], gray[:, 0], gray[:, -1]))
    histogram = np.bincount(border.astype(np.uint8), minlength=256)
    background = int(np.argmax(histogram))
    masked = gray.copy()
    symbol_mask = np.zeros((height, width), dtype=np.uint8)
    text_mask = np.zeros((height, width), dtype=np.uint8)

    for box, target in ((box, symbol_mask) for box in symbol_boxes):
        clipped = _clip_bbox(box, width, height)
        if clipped is not None:
            x1, y1, x2, y2 = clipped
            masked[y1:y2, x1:x2] = background
            target[y1:y2, x1:x2] = 255
    for box, target in ((box, text_mask) for box in text_boxes):
        clipped = _clip_bbox(box, width, height)
        if clipped is not None:
            x1, y1, x2, y2 = clipped
            masked[y1:y2, x1:x2] = background
            target[y1:y2, x1:x2] = 255
    return masked, symbol_mask, text_mask


def binarize(gray: np.ndarray, threshold: int) -> tuple[np.ndarray, int]:
    """Return white-foreground binary pixels and the threshold actually used."""

    if threshold == 0:
        used, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    else:
        used, binary = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY_INV)
    return binary, int(round(used))


def _zhang_suen_numpy(binary: np.ndarray) -> np.ndarray:
    """Vectorized Zhang-Suen thinning fallback for OpenCV non-contrib builds."""

    image = (binary > 0).astype(np.uint8)
    while True:
        padded = np.pad(image, 1, mode="constant")
        neighbours = [
            padded[:-2, 1:-1],
            padded[:-2, 2:],
            padded[1:-1, 2:],
            padded[2:, 2:],
            padded[2:, 1:-1],
            padded[2:, :-2],
            padded[1:-1, :-2],
            padded[:-2, :-2],
        ]
        transitions = sum(
            ((neighbours[index] == 0) & (neighbours[(index + 1) % 8] == 1))
            for index in range(8)
        )
        neighbour_count = sum(neighbours)
        remove = (
            (image == 1)
            & (neighbour_count >= 2)
            & (neighbour_count <= 6)
            & (transitions == 1)
            & ((neighbours[0] * neighbours[2] * neighbours[4]) == 0)
            & ((neighbours[2] * neighbours[4] * neighbours[6]) == 0)
        )
        changed = bool(np.any(remove))
        image[remove] = 0

        padded = np.pad(image, 1, mode="constant")
        neighbours = [
            padded[:-2, 1:-1],
            padded[:-2, 2:],
            padded[1:-1, 2:],
            padded[2:, 2:],
            padded[2:, 1:-1],
            padded[2:, :-2],
            padded[1:-1, :-2],
            padded[:-2, :-2],
        ]
        transitions = sum(
            ((neighbours[index] == 0) & (neighbours[(index + 1) % 8] == 1))
            for index in range(8)
        )
        neighbour_count = sum(neighbours)
        remove = (
            (image == 1)
            & (neighbour_count >= 2)
            & (neighbour_count <= 6)
            & (transitions == 1)
            & ((neighbours[0] * neighbours[2] * neighbours[6]) == 0)
            & ((neighbours[0] * neighbours[4] * neighbours[6]) == 0)
        )
        changed = bool(np.any(remove)) or changed
        image[remove] = 0
        if not changed:
            break
    return image.astype(np.uint8) * 255


def thin(binary: np.ndarray, enabled: bool = True) -> tuple[np.ndarray, str]:
    if not enabled:
        return binary.copy(), "disabled"
    ximgproc = getattr(cv2, "ximgproc", None)
    if ximgproc is not None and hasattr(ximgproc, "thinning"):
        thinning_type = getattr(ximgproc, "THINNING_ZHANGSUEN", 0)
        return ximgproc.thinning(binary, thinningType=thinning_type), "opencv_zhang_suen"
    return _zhang_suen_numpy(binary), "numpy_zhang_suen"


def _runs(values: np.ndarray, max_gap: int) -> Iterable[tuple[int, int]]:
    """Yield inclusive runs after bridging foreground gaps up to max_gap."""

    indices = np.flatnonzero(values > 0)
    if len(indices) == 0:
        return
    start = previous = int(indices[0])
    for raw_index in indices[1:]:
        index = int(raw_index)
        if index - previous - 1 > max_gap:
            yield start, previous
            start = index
        previous = index
    yield start, previous


def detect_axis_segments(skeleton: np.ndarray, min_length: float, merge_gap: float) -> list[Segment]:
    """Detect horizontal and vertical segments by traversing skeleton rows/columns."""

    gap = max(0, int(round(merge_gap)))
    segments: list[Segment] = []
    for y, row in enumerate(skeleton):
        for start, end in _runs(row, gap):
            if end - start + 1 >= min_length:
                segments.append(Segment(start, y, end, y, "horizontal"))
    for x, column in enumerate(skeleton.T):
        for start, end in _runs(column, gap):
            if end - start + 1 >= min_length:
                segments.append(Segment(x, start, x, end, "vertical"))
    return segments


def detect_diagonal_segments(
    skeleton: np.ndarray,
    threshold: int,
    min_length: float,
    merge_gap: float,
    angle_tolerance: float,
    rho: float,
    theta_degrees: float,
) -> list[Segment]:
    """Detect non-axis-aligned segments with probabilistic Hough transform."""

    lines = cv2.HoughLinesP(
        skeleton,
        rho=rho,
        theta=math.radians(theta_degrees),
        threshold=threshold,
        minLineLength=max(1, int(round(min_length))),
        maxLineGap=max(0, int(round(merge_gap))),
    )
    if lines is None:
        return []

    segments: list[Segment] = []
    # OpenCV 4 commonly returns (N, 1, 4), while newer builds may return
    # (N, 4). Reshaping keeps the baseline compatible with both forms.
    for line in np.asarray(lines).reshape(-1, 4):
        x1, y1, x2, y2 = (float(value) for value in line)
        angle = abs(math.degrees(math.atan2(y2 - y1, x2 - x1))) % 180.0
        near_horizontal = min(angle, 180.0 - angle) <= angle_tolerance
        near_vertical = abs(angle - 90.0) <= angle_tolerance
        if near_horizontal or near_vertical:
            continue
        candidate = Segment(x1, y1, x2, y2, "diagonal")
        if candidate.length >= min_length:
            segments.append(candidate)
    return segments


def _canonical(segment: Segment) -> Segment:
    if segment.orientation == "vertical":
        if segment.y1 > segment.y2:
            return Segment(segment.x2, segment.y2, segment.x1, segment.y1, segment.orientation)
    elif segment.x1 > segment.x2 or (segment.x1 == segment.x2 and segment.y1 > segment.y2):
        return Segment(segment.x2, segment.y2, segment.x1, segment.y1, segment.orientation)
    return segment


def _angle_difference(first: float, second: float) -> float:
    delta = abs(first - second) % 180.0
    return min(delta, 180.0 - delta)


def _mergeable(first: Segment, second: Segment, merge_gap: float, merge_distance: float, angle_tolerance: float) -> bool:
    if first.orientation != second.orientation:
        return False
    if _angle_difference(first.angle, second.angle) > angle_tolerance:
        return False
    first = _canonical(first)
    second = _canonical(second)

    if first.orientation == "horizontal":
        first_low, first_high = sorted((first.x1, first.x2))
        second_low, second_high = sorted((second.x1, second.x2))
        gap = max(0.0, max(first_low, second_low) - min(first_high, second_high))
        return abs(first.y1 - second.y1) <= merge_distance and gap <= merge_gap
    if first.orientation == "vertical":
        first_low, first_high = sorted((first.y1, first.y2))
        second_low, second_high = sorted((second.y1, second.y2))
        gap = max(0.0, max(first_low, second_low) - min(first_high, second_high))
        return abs(first.x1 - second.x1) <= merge_distance and gap <= merge_gap

    dx = first.x2 - first.x1
    dy = first.y2 - first.y1
    length = math.hypot(dx, dy)
    if length == 0:
        return False
    ux, uy = dx / length, dy / length

    def projection(x: float, y: float) -> float:
        return (x - first.x1) * ux + (y - first.y1) * uy

    def perpendicular_distance(x: float, y: float) -> float:
        return abs((x - first.x1) * uy - (y - first.y1) * ux)

    distance = max(
        perpendicular_distance(second.x1, second.y1),
        perpendicular_distance(second.x2, second.y2),
    )
    first_interval = sorted((projection(first.x1, first.y1), projection(first.x2, first.y2)))
    second_interval = sorted((projection(second.x1, second.y1), projection(second.x2, second.y2)))
    gap = max(0.0, max(first_interval[0], second_interval[0]) - min(first_interval[1], second_interval[1]))
    return distance <= merge_distance and gap <= merge_gap


def _merge_pair(first: Segment, second: Segment) -> Segment:
    first = _canonical(first)
    second = _canonical(second)
    if first.orientation == "horizontal":
        return Segment(
            min(first.x1, first.x2, second.x1, second.x2),
            (first.y1 + second.y1) / 2.0,
            max(first.x1, first.x2, second.x1, second.x2),
            (first.y1 + second.y1) / 2.0,
            first.orientation,
        )
    if first.orientation == "vertical":
        return Segment(
            (first.x1 + second.x1) / 2.0,
            min(first.y1, first.y2, second.y1, second.y2),
            (first.x1 + second.x1) / 2.0,
            max(first.y1, first.y2, second.y2),
            first.orientation,
        )

    dx = first.x2 - first.x1
    dy = first.y2 - first.y1
    length = math.hypot(dx, dy)
    ux, uy = dx / length, dy / length
    points = [(first.x1, first.y1), (first.x2, first.y2), (second.x1, second.y1), (second.x2, second.y2)]
    projections = [x * ux + y * uy for x, y in points]
    base_projection = first.x1 * ux + first.y1 * uy
    low, high = min(projections), max(projections)
    return Segment(
        first.x1 + (low - base_projection) * ux,
        first.y1 + (low - base_projection) * uy,
        first.x1 + (high - base_projection) * ux,
        first.y1 + (high - base_projection) * uy,
        first.orientation,
    )


def merge_segments(
    segments: Sequence[Segment],
    merge_gap: float,
    merge_distance: float,
    angle_tolerance: float,
    min_length: float,
) -> list[Segment]:
    """Greedily merge near-collinear same-direction segments until stable."""

    merged = [_canonical(segment) for segment in segments]
    changed = True
    while changed:
        changed = False
        result: list[Segment] = []
        for candidate in merged:
            match_index = next(
                (
                    index
                    for index, existing in enumerate(result)
                    if _mergeable(existing, candidate, merge_gap, merge_distance, angle_tolerance)
                ),
                None,
            )
            if match_index is None:
                result.append(candidate)
            else:
                result[match_index] = _merge_pair(result[match_index], candidate)
                changed = True
        merged = result
    return [segment for segment in merged if segment.length >= min_length]


def serialize_segments(segments: Sequence[Segment]) -> list[dict[str, Any]]:
    order = {"horizontal": 0, "vertical": 1, "diagonal": 2}
    ordered = sorted(
        segments,
        key=lambda segment: (
            order[segment.orientation],
            round(min(segment.y1, segment.y2), 2),
            round(min(segment.x1, segment.x2), 2),
        ),
    )
    return [
        {
            "id": f"line_{index:03d}",
            "start": [round(segment.x1, 2), round(segment.y1, 2)],
            "end": [round(segment.x2, 2), round(segment.y2, 2)],
            "orientation": segment.orientation,
        }
        for index, segment in enumerate(ordered, start=1)
    ]


def draw_overlay(
    image: np.ndarray,
    symbol_mask: np.ndarray,
    text_mask: np.ndarray,
    segments: Sequence[Segment],
) -> np.ndarray:
    """Render symbol/text masks and detected lines on the original image."""

    rendered = image.copy().astype(np.float32)
    symbol_color = np.array((40, 40, 230), dtype=np.float32)  # red in BGR
    text_color = np.array((230, 120, 30), dtype=np.float32)  # blue/orange in BGR
    symbol_pixels = symbol_mask > 0
    text_pixels = (text_mask > 0) & ~symbol_pixels
    rendered[symbol_pixels] = rendered[symbol_pixels] * 0.55 + symbol_color * 0.45
    rendered[text_pixels] = rendered[text_pixels] * 0.55 + text_color * 0.45
    rendered = np.clip(rendered, 0, 255).astype(np.uint8)

    height, width = rendered.shape[:2]
    thickness = max(1, min(height, width) // 1200)
    for segment in segments:
        color = {
            "horizontal": (0, 190, 0),
            "vertical": (255, 80, 0),
            "diagonal": (0, 165, 255),
        }[segment.orientation]
        cv2.line(
            rendered,
            (round(segment.x1), round(segment.y1)),
            (round(segment.x2), round(segment.y2)),
            color,
            thickness=max(2, thickness),
            lineType=cv2.LINE_AA,
        )
    return rendered


def _write_image(path: Path, image: np.ndarray) -> None:
    if not cv2.imwrite(str(path), image):
        raise RuntimeError(f"Could not write image: {path}")


def detect_page(
    image: np.ndarray,
    symbol_boxes: Sequence[BBox],
    text_boxes: Sequence[BBox],
    args: argparse.Namespace,
    output_dir: Path,
    page_number: int,
) -> PageResult:
    masked, symbol_mask, text_mask = mask_regions(image, symbol_boxes, text_boxes)
    binary, used_threshold = binarize(masked, args.binary_threshold)
    skeleton, thinning_method = thin(binary, args.thinning)
    axis_segments = detect_axis_segments(skeleton, args.min_line_length, args.merge_gap)
    diagonal_segments = detect_diagonal_segments(
        skeleton,
        threshold=args.threshold,
        min_length=args.min_line_length,
        merge_gap=args.merge_gap,
        angle_tolerance=args.angle_tolerance,
        rho=args.hough_rho,
        theta_degrees=args.hough_theta_degrees,
    )
    segments = merge_segments(
        [*axis_segments, *diagonal_segments],
        merge_gap=args.merge_gap,
        merge_distance=args.merge_distance,
        angle_tolerance=args.angle_tolerance,
        min_length=args.min_line_length,
    )
    lines = serialize_segments(segments)

    stem = f"page-{page_number:03d}"
    masked_name = f"{stem}_masked.png"
    binary_name = f"{stem}_binary.png"
    thinned_name = f"{stem}_thinned.png"
    overlay_name = f"{stem}_line_overlay.png"
    _write_image(output_dir / masked_name, masked)
    _write_image(output_dir / binary_name, binary)
    _write_image(output_dir / thinned_name, skeleton)
    _write_image(output_dir / overlay_name, draw_overlay(image, symbol_mask, text_mask, segments))

    # Kept in the debug JSON so a run is reproducible without inspecting CLI output.
    setattr(args, "_used_threshold", used_threshold)
    setattr(args, "_thinning_method", thinning_method)
    return PageResult(
        page_number=page_number,
        image_size=(image.shape[1], image.shape[0]),
        lines=tuple(lines),
        overlay_name=overlay_name,
        masked_name=masked_name,
        binary_name=binary_name,
        thinned_name=thinned_name,
        symbol_count=len(symbol_boxes),
        text_count=len(text_boxes),
        binary_threshold_used=used_threshold,
        thinning_method=thinning_method,
    )


def _config(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "threshold": args.threshold,
        "binary_threshold": args.binary_threshold,
        "binary_threshold_used": getattr(args, "_used_threshold", None),
        "min_line_length": args.min_line_length,
        "merge_gap": args.merge_gap,
        "merge_distance": args.merge_distance,
        "angle_tolerance": args.angle_tolerance,
        "hough_rho": args.hough_rho,
        "hough_theta_degrees": args.hough_theta_degrees,
        "thinning": args.thinning,
        "thinning_method": getattr(args, "_thinning_method", None),
    }


def run(args: argparse.Namespace) -> Path:
    validate_args(args)
    output_dir = args.output_dir or DEFAULT_OUTPUT_ROOT / args.source.stem
    output_dir.mkdir(parents=True, exist_ok=True)
    symbols_document = _load_json(args.symbols)
    texts_document = _load_json(args.texts)
    page_results: list[PageResult] = []

    for page in iter_input_pages(args.source, args.dpi, args.pages):
        symbol_boxes = _extract_boxes(symbols_document, page.page_number, "detections")
        text_boxes = _extract_boxes(texts_document, page.page_number, "texts")
        page_results.append(
            detect_page(
                page.image,
                symbol_boxes,
                text_boxes,
                args,
                output_dir,
                page.page_number,
            )
        )

    page_payloads = [
        {
            "page_number": result.page_number,
            "image_size": {"width": result.image_size[0], "height": result.image_size[1]},
            "symbol_count": result.symbol_count,
            "text_count": result.text_count,
            "binary_threshold_used": result.binary_threshold_used,
            "thinning_method": result.thinning_method,
            "line_count": len(result.lines),
            "masked_image": result.masked_name,
            "binary_image": result.binary_name,
            "thinned_image": result.thinned_name,
            "overlay_image": result.overlay_name,
            "lines": list(result.lines),
        }
        for result in page_results
    ]
    output: dict[str, Any] = {
        "source": str(args.source.resolve()),
        "input_type": "pdf" if args.source.suffix.lower() == ".pdf" else "image",
        "config": _config(args),
    }
    if len(page_payloads) == 1 and args.source.suffix.lower() != ".pdf":
        output.update(page_payloads[0])
    else:
        output["pages"] = page_payloads
    result_path = output_dir / "lines.json"
    result_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return result_path


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result_path = run(args)
    with result_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if "pages" in payload:
        count = sum(page.get("line_count", 0) for page in payload["pages"])
    else:
        count = payload.get("line_count", 0)
    print(f"Line detection results written to: {result_path.resolve()} ({count} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
