"""Local text extraction/OCR baseline for P&ID drawings.

The module is intentionally independent from symbol detection.  It accepts a
source image or PDF and emits text boxes in the source page's pixel
coordinates, which lets a later line-detection stage consume both symbol and
text boxes as masks without importing an OCR implementation.

PDF pages with a text layer use PyMuPDF directly.  Raster images (and scanned
PDF pages when the optional fallback is enabled) use PaddleOCR's lightweight
PP-OCRv5 detector and English recognizer on overlapping tiles.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

import cv2
import numpy as np

from tiled_inference import generate_tiles, parse_page_numbers, read_image


IMAGE_SUFFIXES = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_ROOT = REPOSITORY_ROOT / "artifacts" / "ocr-baseline"

TEXT_DETECTION_MODEL = "PP-OCRv5_mobile_det"
# PaddleX 3.0 ships the English mobile recognizer through the v4 family.
# Keep the v5 detector, but use the latest English recognizer exposed by the
# installed pipeline so the raster OCR step can run in the Docker runtime.
TEXT_RECOGNITION_MODEL = "en_PP-OCRv4_mobile_rec"


@dataclass
class TextDetection:
    """One normalized text detection in global source-image coordinates."""

    text: str
    bbox: tuple[float, float, float, float]
    confidence: float
    source: str

    def as_dict(self, text_id: str) -> dict[str, Any]:
        return {
            "id": text_id,
            "text": self.text,
            "bbox": [round(value, 2) for value in self.bbox],
            "confidence": round(float(self.confidence), 6),
            "source": self.source,
        }


@dataclass(frozen=True)
class PageResult:
    """Intermediate page result before document-wide text IDs are assigned."""

    page_number: int
    image: np.ndarray
    detections: tuple[TextDetection, ...]
    source_mode: str
    tile_count: int
    overlay_name: str


def normalize_text(value: Any) -> str:
    """Collapse OCR/PDF whitespace without applying domain-specific correction."""

    return " ".join(str(value or "").split()).strip()


def clip_bbox(
    bbox: Sequence[float],
    image_width: int,
    image_height: int,
) -> tuple[float, float, float, float] | None:
    """Convert a box to clipped xyxy coordinates and reject degenerate boxes."""

    if len(bbox) != 4:
        return None
    x1, y1, x2, y2 = (float(value) for value in bbox)
    left = max(0.0, min(float(image_width), min(x1, x2)))
    top = max(0.0, min(float(image_height), min(y1, y2)))
    right = max(0.0, min(float(image_width), max(x1, x2)))
    bottom = max(0.0, min(float(image_height), max(y1, y2)))
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def polygon_to_bbox(
    polygon: Sequence[Sequence[float]],
    offset_x: float = 0.0,
    offset_y: float = 0.0,
) -> tuple[float, float, float, float] | None:
    """Convert PaddleOCR's quadrilateral polygon to a tile/global xyxy box."""

    points = [(float(point[0]), float(point[1])) for point in polygon if len(point) >= 2]
    if not points:
        return None
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return min(xs) + offset_x, min(ys) + offset_y, max(xs) + offset_x, max(ys) + offset_y


def bbox_iou(first: Sequence[float], second: Sequence[float]) -> float:
    """Compute IoU for two xyxy boxes."""

    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[2], second[2])
    bottom = min(first[3], second[3])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    if intersection <= 0.0:
        return 0.0
    first_area = max(0.0, first[2] - first[0]) * max(0.0, first[3] - first[1])
    second_area = max(0.0, second[2] - second[0]) * max(0.0, second[3] - second[1])
    union = first_area + second_area - intersection
    return intersection / union if union > 0.0 else 0.0


def bbox_overlap_ratio(first: Sequence[float], second: Sequence[float]) -> float:
    """Return intersection divided by the smaller box area."""

    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[2], second[2])
    bottom = min(first[3], second[3])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    first_area = max(0.0, first[2] - first[0]) * max(0.0, first[3] - first[1])
    second_area = max(0.0, second[2] - second[0]) * max(0.0, second[3] - second[1])
    smaller_area = min(first_area, second_area)
    return intersection / smaller_area if smaller_area > 0.0 else 0.0


def _canonical_text(text: str) -> str:
    """Use only for duplicate matching; the emitted text is never corrected."""

    return normalize_text(text).casefold()


def merge_text_detections(
    detections: Sequence[TextDetection],
    iou_threshold: float = 0.40,
    overlap_threshold: float = 0.65,
) -> list[TextDetection]:
    """Merge duplicate text boxes produced by overlapping tiles.

    Matching is text-aware to avoid merging adjacent repeated labels.  The
    highest-confidence text is retained while the merged box covers the union
    of the duplicate boxes.
    """

    clusters: list[TextDetection] = []
    for candidate in sorted(detections, key=lambda item: item.confidence, reverse=True):
        match = None
        for cluster in clusters:
            if _canonical_text(cluster.text) != _canonical_text(candidate.text):
                continue
            if (
                bbox_iou(cluster.bbox, candidate.bbox) >= iou_threshold
                or bbox_overlap_ratio(cluster.bbox, candidate.bbox) >= overlap_threshold
            ):
                match = cluster
                break

        if match is None:
            clusters.append(candidate)
            continue

        match.bbox = (
            min(match.bbox[0], candidate.bbox[0]),
            min(match.bbox[1], candidate.bbox[1]),
            max(match.bbox[2], candidate.bbox[2]),
            max(match.bbox[3], candidate.bbox[3]),
        )
        if candidate.confidence > match.confidence:
            match.text = candidate.text
            match.confidence = candidate.confidence
            match.source = candidate.source

    return sorted(clusters, key=lambda item: (item.bbox[1], item.bbox[0], item.text.casefold()))


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_python(value: Any) -> Any:
    """Convert Paddle tensors/arrays to JSON-like Python values."""

    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, dict):
        return {key: _to_python(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_python(item) for item in value]
    return value


def _payload_from_paddle_result(result: Any) -> Any:
    """Support PaddleOCR 3.x Result objects and the older list-shaped result."""

    payload = result
    if hasattr(payload, "json"):
        json_value = payload.json
        json_value = json_value() if callable(json_value) else json_value
        if isinstance(json_value, str):
            try:
                payload = json.loads(json_value)
            except json.JSONDecodeError:
                pass
        elif json_value is not None:
            payload = json_value
    if hasattr(payload, "res"):
        payload = payload.res
    return _to_python(payload)


def parse_paddle_result(result: Any) -> list[tuple[str, Sequence[Sequence[float]], float]]:
    """Extract text, polygon, score tuples from PaddleOCR result variants."""

    payload = _payload_from_paddle_result(result)
    if isinstance(payload, dict) and isinstance(payload.get("res"), dict):
        payload = payload["res"]

    if isinstance(payload, dict):
        polygons = payload.get("dt_polys")
        if polygons is None:
            polygons = payload.get("rec_polys")
        if polygons is None:
            polygons = payload.get("dt_boxes")
        polygons = polygons or []
        texts = payload.get("rec_texts")
        if texts is None:
            texts = payload.get("texts")
        texts = texts or []
        scores = payload.get("rec_scores")
        if scores is None:
            scores = payload.get("scores")
        scores = scores or []
        return [
            (normalize_text(texts[index]), polygons[index], _safe_float(scores[index], 0.0) if index < len(scores) else 0.0)
            for index in range(min(len(polygons), len(texts)))
            if normalize_text(texts[index])
        ]

    # PaddleOCR 2.x shape: [[[[x,y], ...], (text, score)], ...].
    if isinstance(payload, list) and len(payload) == 1 and isinstance(payload[0], list):
        payload = payload[0]
    parsed: list[tuple[str, Sequence[Sequence[float]], float]] = []
    if isinstance(payload, list):
        for item in payload:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            polygon, recognition = item[0], item[1]
            if isinstance(recognition, (list, tuple)):
                text = normalize_text(recognition[0] if recognition else "")
                score = _safe_float(recognition[1], 0.0) if len(recognition) > 1 else 0.0
            else:
                text, score = normalize_text(recognition), 0.0
            if text:
                parsed.append((text, polygon, score))
    return parsed


class PaddleOcrRunner:
    """Lazy PaddleOCR adapter so PDF text extraction needs no Paddle install."""

    def __init__(self, device: str = "cpu") -> None:
        try:
            from paddleocr import PaddleOCR
        except ImportError as exc:
            raise RuntimeError(
                "Raster OCR requires paddleocr and paddlepaddle. "
                f"Current Python is {sys.version_info.major}.{sys.version_info.minor}. "
                "On Windows, use Python 3.13 and run scripts/bootstrap-ocr.ps1."
            ) from exc

        self._ocr = PaddleOCR(
            text_detection_model_name=TEXT_DETECTION_MODEL,
            text_recognition_model_name=TEXT_RECOGNITION_MODEL,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            device=device,
        )

    def predict(self, image: np.ndarray) -> Iterable[Any]:
        return self._ocr.predict(image)


def ocr_raster_image(
    image: np.ndarray,
    ocr_runner: Any,
    tile_size: int,
    overlap: float,
    min_confidence: float,
    merge_iou: float,
    merge_overlap: float,
) -> tuple[list[TextDetection], int, int]:
    """Run PaddleOCR on overlapping tiles and map every box to global pixels."""

    image_height, image_width = image.shape[:2]
    raw_detections: list[TextDetection] = []
    tile_count = 0
    for tile_count, tile in enumerate(generate_tiles(image, tile_size, overlap), start=1):
        for result in ocr_runner.predict(tile.image):
            for text, polygon, confidence in parse_paddle_result(result):
                if confidence < min_confidence:
                    continue
                global_bbox = polygon_to_bbox(polygon, offset_x=tile.x, offset_y=tile.y)
                if global_bbox is None:
                    continue
                clipped = clip_bbox(global_bbox, image_width, image_height)
                if clipped is not None:
                    raw_detections.append(
                        TextDetection(
                            text=text,
                            bbox=clipped,
                            confidence=confidence,
                            source="ocr",
                        )
                    )

    merged = merge_text_detections(raw_detections, merge_iou, merge_overlap)
    return merged, tile_count, len(raw_detections)


def _pdf_page_image(page: Any, fitz_module: Any, dpi: int) -> np.ndarray:
    scale = dpi / 72.0
    pixmap = page.get_pixmap(matrix=fitz_module.Matrix(scale, scale), alpha=False)
    rgb = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(pixmap.height, pixmap.width, pixmap.n)
    rgb = rgb[:, :, :3]
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def extract_pdf_text(page: Any, image: np.ndarray, scale: float) -> list[TextDetection]:
    """Extract text spans and map PyMuPDF point coordinates to rendered pixels."""

    image_height, image_width = image.shape[:2]
    detections: list[TextDetection] = []
    text_dict = page.get_text("dict", sort=True)
    for block in text_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = normalize_text(span.get("text", ""))
                if not text:
                    continue
                bbox = span.get("bbox")
                if not bbox or len(bbox) != 4:
                    continue
                scaled_bbox = tuple(float(value) * scale for value in bbox)
                clipped = clip_bbox(scaled_bbox, image_width, image_height)
                if clipped is not None:
                    detections.append(
                        TextDetection(
                            text=text,
                            bbox=clipped,
                            confidence=1.0,
                            source="pdf_text",
                        )
                    )
    return detections


def iter_pdf_pages(source: Path, dpi: int, pages: str) -> Iterator[tuple[int, Any, np.ndarray, float]]:
    """Yield page number, PyMuPDF page, rendered BGR image, and point-to-pixel scale."""

    try:
        import pymupdf as fitz
    except ImportError as exc:
        try:
            import fitz
        except ImportError as fallback_exc:
            raise RuntimeError(
                "PDF support requires PyMuPDF. Install training/yolov8s/ocr-requirements.txt first."
            ) from fallback_exc

    document = fitz.open(str(source))
    try:
        selected_pages = parse_page_numbers(pages, len(document))
        scale = dpi / 72.0
        for page_index in selected_pages:
            page = document[page_index]
            yield page_index + 1, page, _pdf_page_image(page, fitz, dpi), scale
    finally:
        document.close()


def draw_text_overlay(image: np.ndarray, detections: Sequence[TextDetection]) -> np.ndarray:
    """Draw text boxes and readable labels on a full-resolution BGR image."""

    rendered = image.copy()
    thickness = max(2, min(image.shape[:2]) // 1500)
    font_scale = max(0.45, min(image.shape[:2]) / 2400.0)
    for detection in detections:
        x1, y1, x2, y2 = (round(value) for value in detection.bbox)
        color = (0, 180, 0) if detection.source == "pdf_text" else (0, 140, 255)
        cv2.rectangle(rendered, (x1, y1), (x2, y2), color, thickness)
        label = f"{detection.text} [{detection.confidence:.2f}]"
        (label_width, label_height), baseline = cv2.getTextSize(
            label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, max(1, thickness)
        )
        label_top = max(0, y1 - label_height - baseline - 2)
        cv2.rectangle(rendered, (x1, label_top), (x1 + label_width + 4, y1), color, -1)
        cv2.putText(
            rendered,
            label,
            (x1 + 2, max(label_height + 1, y1 - baseline - 1)),
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            (255, 255, 255),
            max(1, thickness),
            cv2.LINE_AA,
        )
    return rendered


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="P&ID image or PDF.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory. Defaults to artifacts/ocr-baseline/<source-stem>.",
    )
    parser.add_argument("--dpi", type=int, default=300, help="PDF render DPI for overlays and OCR fallback.")
    parser.add_argument(
        "--pages",
        default="all",
        help="PDF pages to process, for example: all, 1, or 1,3-5. Ignored for images.",
    )
    parser.add_argument("--tile-size", type=int, default=2048, help="Raster OCR tile edge in source pixels.")
    parser.add_argument("--overlap", type=float, default=0.20, help="Fractional overlap between OCR tiles.")
    parser.add_argument("--min-confidence", type=float, default=0.0, help="Minimum recognition score to emit.")
    parser.add_argument("--merge-iou", type=float, default=0.40, help="IoU threshold for duplicate tile boxes.")
    parser.add_argument(
        "--merge-overlap",
        type=float,
        default=0.65,
        help="Intersection/min-area threshold for duplicate tile boxes.",
    )
    parser.add_argument("--device", default="cpu", help="Paddle device, for example cpu or gpu:0.")
    parser.add_argument(
        "--pdf-ocr-fallback",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Run raster OCR for PDF pages that have no text layer.",
    )
    return parser


def validate_args(args: argparse.Namespace) -> None:
    if not args.source.is_file():
        raise FileNotFoundError(f"Source not found: {args.source}")
    if args.source.suffix.lower() != ".pdf" and args.source.suffix.lower() not in IMAGE_SUFFIXES:
        raise ValueError(f"Unsupported source type: {args.source.suffix}")
    if args.dpi <= 0 or args.tile_size <= 0:
        raise ValueError("dpi and tile-size must be positive.")
    if not 0.0 <= args.overlap < 1.0:
        raise ValueError("overlap must be in [0.0, 1.0).")
    if not 0.0 <= args.min_confidence <= 1.0:
        raise ValueError("min-confidence must be in [0.0, 1.0].")
    if not 0.0 < args.merge_iou <= 1.0 or not 0.0 < args.merge_overlap <= 1.0:
        raise ValueError("merge thresholds must be in (0.0, 1.0].")


def _serialize_pages(page_results: Sequence[PageResult]) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    next_id = 1
    for page_result in page_results:
        height, width = page_result.image.shape[:2]
        texts = []
        for detection in page_result.detections:
            texts.append(detection.as_dict(f"text_{next_id:03d}"))
            next_id += 1
        serialized.append(
            {
                "page_number": page_result.page_number,
                "image_size": {"width": width, "height": height},
                "source_mode": page_result.source_mode,
                "tile_count": page_result.tile_count,
                "text_count": len(texts),
                "overlay_image": page_result.overlay_name,
                "texts": texts,
            }
        )
    return serialized


def _output_root(args: argparse.Namespace) -> Path:
    return args.output_dir or DEFAULT_OUTPUT_ROOT / args.source.stem


def run(args: argparse.Namespace) -> Path:
    """Execute the baseline and return the written JSON path."""

    destination = _output_root(args)
    destination.mkdir(parents=True, exist_ok=True)
    page_results: list[PageResult] = []
    runner: PaddleOcrRunner | None = None

    if args.source.suffix.lower() == ".pdf":
        for page_number, page, image, scale in iter_pdf_pages(args.source, args.dpi, args.pages):
            detections = extract_pdf_text(page, image, scale)
            source_mode = "pdf_text"
            tile_count = 0
            if not detections and args.pdf_ocr_fallback:
                runner = runner or PaddleOcrRunner(args.device)
                detections, tile_count, _ = ocr_raster_image(
                    image,
                    runner,
                    args.tile_size,
                    args.overlap,
                    args.min_confidence,
                    args.merge_iou,
                    args.merge_overlap,
                )
                source_mode = "ocr"
            overlay_name = f"page-{page_number:03d}_overlay.png"
            if not cv2.imwrite(str(destination / overlay_name), draw_text_overlay(image, detections)):
                raise RuntimeError(f"Could not write overlay: {destination / overlay_name}")
            page_results.append(
                PageResult(page_number, image, tuple(detections), source_mode, tile_count, overlay_name)
            )
    else:
        image = read_image(args.source)
        runner = PaddleOcrRunner(args.device)
        detections, tile_count, _ = ocr_raster_image(
            image,
            runner,
            args.tile_size,
            args.overlap,
            args.min_confidence,
            args.merge_iou,
            args.merge_overlap,
        )
        overlay_name = "page-001_overlay.png"
        if not cv2.imwrite(str(destination / overlay_name), draw_text_overlay(image, detections)):
            raise RuntimeError(f"Could not write overlay: {destination / overlay_name}")
        page_results.append(PageResult(1, image, tuple(detections), "ocr", tile_count, overlay_name))

    output = {
        "source": str(args.source.resolve()),
        "input_type": "pdf" if args.source.suffix.lower() == ".pdf" else "image",
        "config": {
            "dpi": args.dpi if args.source.suffix.lower() == ".pdf" else None,
            "tile_size": args.tile_size,
            "overlap": args.overlap,
            "min_confidence": args.min_confidence,
            "merge_iou": args.merge_iou,
            "merge_overlap": args.merge_overlap,
            "text_detection_model": TEXT_DETECTION_MODEL,
            "text_recognition_model": TEXT_RECOGNITION_MODEL,
            "device": args.device,
            "pdf_ocr_fallback": args.pdf_ocr_fallback,
        },
        "pages": _serialize_pages(page_results),
    }
    result_path = destination / "ocr.json"
    result_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return result_path


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    validate_args(args)
    result_path = run(args)
    print(f"OCR results written to: {result_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
