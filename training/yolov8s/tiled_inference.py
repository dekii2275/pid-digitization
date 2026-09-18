"""Run tiled YOLO inference on an image or PDF P&ID and save global results.

The detector is intentionally independent from the legacy FastAPI inference
service. It produces a simple global-coordinate contract that OCR, line
detection, and topology reconstruction can consume later.
"""

from __future__ import annotations

import argparse
import json
import warnings
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Sequence

import cv2
import numpy as np

from class_names import CLASS_NAMES


IMAGE_SUFFIXES = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_PATH = REPOSITORY_ROOT / "models" / "symbol-detector" / "best.pt"
DEFAULT_OUTPUT_ROOT = REPOSITORY_ROOT / "artifacts" / "tiled-inference"


@dataclass(frozen=True)
class Tile:
    """A source-image crop and the position of its top-left corner."""

    image: np.ndarray
    x: int
    y: int


@dataclass(frozen=True)
class InputPage:
    """A single raster image or one rendered PDF page."""

    page_number: int
    image: np.ndarray


@dataclass(frozen=True)
class Detection:
    """A post-mapping detection expressed in source-image pixel coordinates."""

    class_id: int
    class_name: str
    confidence: float
    bbox: tuple[float, float, float, float]

    @property
    def center(self) -> tuple[float, float]:
        x1, y1, x2, y2 = self.bbox
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

    def as_dict(self) -> dict[str, Any]:
        return {
            "class_id": self.class_id,
            "class_name": self.class_name,
            "confidence": round(self.confidence, 6),
            "bbox": [round(value, 2) for value in self.bbox],
            "center": [round(value, 2) for value in self.center],
        }


@dataclass(frozen=True)
class ContentRegion:
    """An inclusive-exclusive rectangular region in global source-image pixels."""

    x1: int
    y1: int
    x2: int
    y2: int

    def contains_center(self, detection: Detection) -> bool:
        center_x, center_y = detection.center
        return self.x1 <= center_x < self.x2 and self.y1 <= center_y < self.y2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="P&ID image or PDF.")
    parser.add_argument("--weights", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Final output directory. Defaults to artifacts/tiled-inference/<source-stem>.",
    )
    parser.add_argument("--dpi", type=int, default=600, help="PDF render resolution.")
    parser.add_argument(
        "--pages",
        default="all",
        help="PDF pages to process, for example: all, 1, or 1,3-5. Ignored for images.",
    )
    parser.add_argument("--tile-size", type=int, default=1024)
    parser.add_argument(
        "--overlap",
        type=float,
        default=0.25,
        help="Fractional overlap between adjacent tiles. 0.25 produces stride 768 for 1024 tiles.",
    )
    parser.add_argument("--imgsz", type=int, default=1024)
    parser.add_argument("--conf", type=float, default=0.15)
    parser.add_argument(
        "--iou",
        type=float,
        default=0.50,
        help="IoU threshold for global class-aware tile merge NMS.",
    )
    parser.add_argument(
        "--tile-iou",
        type=float,
        default=0.70,
        help="IoU threshold for Ultralytics NMS inside each tile.",
    )
    parser.add_argument(
        "--whole-image",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Also infer once on the un-cropped full page before merging with tile detections.",
    )
    parser.add_argument(
        "--whole-imgsz",
        type=int,
        default=1280,
        help="Inference size for the whole-page branch.",
    )
    parser.add_argument(
        "--whole-conf",
        type=float,
        default=0.10,
        help="Confidence threshold for the whole-page branch.",
    )
    parser.add_argument(
        "--whole-iou",
        type=float,
        default=0.70,
        help="Ultralytics NMS IoU threshold for the whole-page branch.",
    )
    parser.add_argument(
        "--content-region",
        default="0,0,0.80,1.0",
        help=(
            "Normalized x1,y1,x2,y2 region to retain. The default excludes the rightmost "
            "20%% technical/title panel; use 0,0,1,1 to retain an entire page."
        ),
    )
    parser.add_argument("--device", default=None, help="For example: 0, cpu, or cuda:0.")
    return parser


def validate_args(args: argparse.Namespace) -> None:
    if not args.source.exists():
        raise FileNotFoundError(f"Source not found: {args.source}")
    if not args.weights.is_file():
        raise FileNotFoundError(f"YOLO weights not found: {args.weights}")
    if args.source.suffix.lower() != ".pdf" and args.source.suffix.lower() not in IMAGE_SUFFIXES:
        supported = ", ".join(sorted(IMAGE_SUFFIXES | {".pdf"}))
        raise ValueError(f"Unsupported source type {args.source.suffix!r}. Supported: {supported}")
    if args.dpi <= 0 or args.tile_size <= 0 or args.imgsz <= 0 or args.whole_imgsz <= 0:
        raise ValueError("dpi, tile-size, imgsz, and whole-imgsz must be positive.")
    if not 0.0 <= args.overlap < 1.0:
        raise ValueError("overlap must be in [0.0, 1.0).")
    if not 0.0 <= args.conf <= 1.0 or not 0.0 <= args.whole_conf <= 1.0:
        raise ValueError("conf and whole-conf must be in [0.0, 1.0].")
    if not all(0.0 < value <= 1.0 for value in (args.iou, args.tile_iou, args.whole_iou)):
        raise ValueError("iou, tile-iou, and whole-iou must be in (0.0, 1.0].")


def resolve_content_region(specification: str, image_width: int, image_height: int) -> ContentRegion:
    """Convert a normalized x1,y1,x2,y2 CLI region into source-image pixel bounds."""

    try:
        values = tuple(float(value.strip()) for value in specification.split(","))
    except ValueError as exc:
        raise ValueError("content-region must have four comma-separated numeric values.") from exc
    if len(values) != 4 or not all(0.0 <= value <= 1.0 for value in values):
        raise ValueError("content-region values must be normalized numbers in [0.0, 1.0].")
    x1, y1, x2, y2 = values
    if x1 >= x2 or y1 >= y2:
        raise ValueError("content-region must satisfy x1 < x2 and y1 < y2.")
    return ContentRegion(
        x1=round(x1 * image_width),
        y1=round(y1 * image_height),
        x2=round(x2 * image_width),
        y2=round(y2 * image_height),
    )


def parse_page_numbers(specification: str, page_count: int) -> list[int]:
    """Return zero-based page indexes from a human-friendly 1-based selection."""

    if specification.strip().lower() == "all":
        return list(range(page_count))

    selected: set[int] = set()
    for token in specification.split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            start_text, end_text = token.split("-", maxsplit=1)
            start, end = int(start_text), int(end_text)
            if start > end:
                raise ValueError(f"Invalid page range: {token}")
            selected.update(range(start - 1, end))
        else:
            selected.add(int(token) - 1)

    invalid = sorted(index + 1 for index in selected if index < 0 or index >= page_count)
    if invalid:
        raise ValueError(f"Requested PDF page(s) outside 1-{page_count}: {invalid}")
    if not selected:
        raise ValueError("No PDF pages were selected.")
    return sorted(selected)


def read_image(path: Path) -> np.ndarray:
    """Load an image through OpenCV while handling Unicode paths on Windows."""

    encoded = np.fromfile(path, dtype=np.uint8)
    image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Could not decode image: {path}")
    return image


def iter_input_pages(source: Path, dpi: int, pages: str) -> Iterator[InputPage]:
    """Yield BGR pages from an image or lazily rendered PDF pages."""

    if source.suffix.lower() != ".pdf":
        yield InputPage(page_number=1, image=read_image(source))
        return

    try:
        import pypdfium2 as pdfium
    except ImportError as exc:
        raise RuntimeError(
            "PDF support requires pypdfium2. Re-run .\\scripts\\bootstrap-yolov8.ps1 "
            "after pulling the updated requirements."
        ) from exc

    document = pdfium.PdfDocument(str(source))
    try:
        selected_pages = parse_page_numbers(pages, len(document))
        scale = dpi / 72.0
        for page_index in selected_pages:
            page = document[page_index]
            bitmap = page.render(scale=scale)
            try:
                rgb_image = np.asarray(bitmap.to_pil().convert("RGB"))
                yield InputPage(
                    page_number=page_index + 1,
                    image=cv2.cvtColor(rgb_image, cv2.COLOR_RGB2BGR),
                )
            finally:
                bitmap.close()
                page.close()
    finally:
        document.close()


def tile_positions(length: int, tile_size: int, stride: int) -> list[int]:
    """Generate starts that cover the final right or bottom source-image edge."""

    if length <= tile_size:
        return [0]
    final_start = length - tile_size
    positions = list(range(0, final_start + 1, stride))
    if positions[-1] != final_start:
        positions.append(final_start)
    return positions


def generate_tiles(
    image: np.ndarray,
    tile_size: int,
    overlap: float,
    origin_x: int = 0,
    origin_y: int = 0,
) -> Iterator[Tile]:
    """Yield overlapping source-image crops with their global top-left positions."""

    stride = max(1, round(tile_size * (1.0 - overlap)))
    height, width = image.shape[:2]
    for y in tile_positions(height, tile_size, stride):
        for x in tile_positions(width, tile_size, stride):
            yield Tile(
                image=image[y : y + tile_size, x : x + tile_size],
                x=x + origin_x,
                y=y + origin_y,
            )


def model_class_names(model: Any) -> dict[int, str]:
    """Prefer class names embedded in the checkpoint, with the training map as fallback."""

    raw_names = getattr(model, "names", None)
    if isinstance(raw_names, dict):
        names = {int(class_id): str(name) for class_id, name in raw_names.items()}
    elif isinstance(raw_names, (list, tuple)):
        names = {class_id: str(name) for class_id, name in enumerate(raw_names)}
    else:
        names = {}

    expected = {class_id: name for class_id, name in enumerate(CLASS_NAMES)}
    if names and names != expected:
        warnings.warn(
            "Checkpoint class names differ from training/yolov8s/class_names.py; "
            "using class names embedded in the checkpoint.",
            stacklevel=2,
        )
    return names or expected


def map_tile_detection(
    class_id: int,
    class_name: str,
    confidence: float,
    tile_bbox: Sequence[float],
    tile: Tile,
    image_width: int,
    image_height: int,
) -> Detection:
    """Translate a tile-local xyxy box into clipped global source-image coordinates."""

    x1, y1, x2, y2 = tile_bbox
    return Detection(
        class_id=class_id,
        class_name=class_name,
        confidence=confidence,
        bbox=(
            max(0.0, min(float(image_width), x1 + tile.x)),
            max(0.0, min(float(image_height), y1 + tile.y)),
            max(0.0, min(float(image_width), x2 + tile.x)),
            max(0.0, min(float(image_height), y2 + tile.y)),
        ),
    )


def detect_tiles(
    model: Any,
    image: np.ndarray,
    tile_size: int,
    overlap: float,
    imgsz: int,
    conf: float,
    tile_iou: float,
    device: str | None,
    origin_x: int = 0,
    origin_y: int = 0,
    global_image_width: int | None = None,
    global_image_height: int | None = None,
) -> tuple[list[Detection], int]:
    """Run the model on each tile and map all local detections to global coordinates."""

    height, width = image.shape[:2]
    map_width = global_image_width if global_image_width is not None else width
    map_height = global_image_height if global_image_height is not None else height
    class_names = model_class_names(model)
    detections: list[Detection] = []
    tile_count = 0
    for tile_count, tile in enumerate(
        generate_tiles(image, tile_size, overlap, origin_x=origin_x, origin_y=origin_y), start=1
    ):
        result = model.predict(
            source=tile.image,
            imgsz=imgsz,
            conf=conf,
            iou=tile_iou,
            device=device,
            save=False,
            verbose=False,
        )[0]
        if result.boxes is None or len(result.boxes) == 0:
            continue
        for box, score, class_id in zip(
            result.boxes.xyxy.cpu().tolist(),
            result.boxes.conf.cpu().tolist(),
            result.boxes.cls.cpu().tolist(),
        ):
            integer_class_id = int(class_id)
            detections.append(
                map_tile_detection(
                    class_id=integer_class_id,
                    class_name=class_names.get(integer_class_id, f"class_{integer_class_id}"),
                    confidence=float(score),
                    tile_bbox=box,
                    tile=tile,
                    image_width=map_width,
                    image_height=map_height,
                )
            )
    return detections, tile_count


def detect_whole_image(
    model: Any,
    image: np.ndarray,
    imgsz: int,
    conf: float,
    iou: float,
    device: str | None,
) -> list[Detection]:
    """Run the checkpoint once on the unchanged full page to retain its trained scale/context."""

    height, width = image.shape[:2]
    class_names = model_class_names(model)
    result = model.predict(
        source=image,
        imgsz=imgsz,
        conf=conf,
        iou=iou,
        device=device,
        save=False,
        verbose=False,
    )[0]
    if result.boxes is None or len(result.boxes) == 0:
        return []

    whole_page = Tile(image=image, x=0, y=0)
    return [
        map_tile_detection(
            class_id=int(class_id),
            class_name=class_names.get(int(class_id), f"class_{int(class_id)}"),
            confidence=float(score),
            tile_bbox=box,
            tile=whole_page,
            image_width=width,
            image_height=height,
        )
        for box, score, class_id in zip(
            result.boxes.xyxy.cpu().tolist(),
            result.boxes.conf.cpu().tolist(),
            result.boxes.cls.cpu().tolist(),
        )
    ]


def bbox_iou(first: Sequence[float], second: Sequence[float]) -> float:
    """Compute IoU for two xyxy bounding boxes."""

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


def class_aware_nms(detections: Sequence[Detection], iou_threshold: float) -> list[Detection]:
    """Keep high-confidence boxes, suppressing only overlapping boxes of the same class."""

    per_class: dict[int, list[Detection]] = defaultdict(list)
    for detection in detections:
        per_class[detection.class_id].append(detection)

    kept: list[Detection] = []
    for class_id in sorted(per_class):
        candidates = sorted(per_class[class_id], key=lambda item: item.confidence, reverse=True)
        while candidates:
            best = candidates.pop(0)
            kept.append(best)
            candidates = [
                candidate
                for candidate in candidates
                if bbox_iou(best.bbox, candidate.bbox) < iou_threshold
            ]
    return sorted(kept, key=lambda item: item.confidence, reverse=True)


def class_color(class_id: int) -> tuple[int, int, int]:
    """Return a stable, high-contrast BGR color without creating a palette file."""

    hue = (class_id * 37) % 180
    color = cv2.cvtColor(np.uint8([[[hue, 220, 255]]]), cv2.COLOR_HSV2BGR)[0, 0]
    return tuple(int(value) for value in color)


def draw_detections(image: np.ndarray, detections: Sequence[Detection]) -> np.ndarray:
    """Draw unlabeled bounding boxes on a full-resolution image."""

    rendered = image.copy()
    thickness = max(2, min(image.shape[:2]) // 1500)
    for detection in detections:
        x1, y1, x2, y2 = (round(value) for value in detection.bbox)
        cv2.rectangle(rendered, (x1, y1), (x2, y2), class_color(detection.class_id), thickness)
    return rendered


def output_directory(args: argparse.Namespace) -> Path:
    return args.output_dir if args.output_dir is not None else DEFAULT_OUTPUT_ROOT / args.source.stem


def build_output_document(
    source: Path,
    args: argparse.Namespace,
    page_results: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    stride = max(1, round(args.tile_size * (1.0 - args.overlap)))
    return {
        "source": str(source.resolve()),
        "input_type": "pdf" if source.suffix.lower() == ".pdf" else "image",
        "config": {
            "dpi": args.dpi if source.suffix.lower() == ".pdf" else None,
            "tile_size": args.tile_size,
            "overlap": args.overlap,
            "stride": stride,
            "imgsz": args.imgsz,
            "confidence_threshold": args.conf,
            "global_nms_iou_threshold": args.iou,
            "tile_nms_iou_threshold": args.tile_iou,
            "whole_image_enabled": args.whole_image,
            "whole_imgsz": args.whole_imgsz if args.whole_image else None,
            "whole_confidence_threshold": args.whole_conf if args.whole_image else None,
            "whole_nms_iou_threshold": args.whole_iou if args.whole_image else None,
            "content_region": args.content_region,
            "weights": str(args.weights.resolve()),
        },
        "pages": list(page_results),
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    validate_args(args)

    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise RuntimeError(
            "YOLO dependencies are missing. Run .\\scripts\\bootstrap-yolov8.ps1 first."
        ) from exc

    destination = output_directory(args)
    destination.mkdir(parents=True, exist_ok=True)
    model = YOLO(str(args.weights))
    page_results: list[dict[str, Any]] = []
    for input_page in iter_input_pages(args.source, args.dpi, args.pages):
        height, width = input_page.image.shape[:2]
        content_region = resolve_content_region(args.content_region, width, height)
        content_image = input_page.image[
            content_region.y1 : content_region.y2,
            content_region.x1 : content_region.x2,
        ]
        raw_detections, tile_count = detect_tiles(
            model=model,
            image=content_image,
            tile_size=args.tile_size,
            overlap=args.overlap,
            imgsz=args.imgsz,
            conf=args.conf,
            tile_iou=args.tile_iou,
            device=args.device,
            origin_x=content_region.x1,
            origin_y=content_region.y1,
            global_image_width=width,
            global_image_height=height,
        )
        whole_page_detections = []
        if args.whole_image:
            whole_page_detections = [
                detection
                for detection in detect_whole_image(
                    model=model,
                    image=input_page.image,
                    imgsz=args.whole_imgsz,
                    conf=args.whole_conf,
                    iou=args.whole_iou,
                    device=args.device,
                )
                if content_region.contains_center(detection)
            ]
        merged_detections = class_aware_nms(raw_detections + whole_page_detections, args.iou)
        overlay_name = f"page-{input_page.page_number:03d}_overlay.jpg"
        overlay_path = destination / overlay_name
        if not cv2.imwrite(str(overlay_path), draw_detections(input_page.image, merged_detections)):
            raise RuntimeError(f"Could not write overlay: {overlay_path}")

        page_results.append(
            {
                "page_number": input_page.page_number,
                "image_size": {"width": width, "height": height},
                "tile_count": tile_count,
                "content_region": {
                    "x1": content_region.x1,
                    "y1": content_region.y1,
                    "x2": content_region.x2,
                    "y2": content_region.y2,
                },
                "tile_detections_before_global_nms": len(raw_detections),
                "whole_image_detections_before_global_nms": len(whole_page_detections),
                "detections_before_global_nms": len(raw_detections) + len(whole_page_detections),
                "detections_after_global_nms": len(merged_detections),
                "overlay_image": overlay_name,
                "detections": [detection.as_dict() for detection in merged_detections],
            }
        )
        print(
            f"Page {input_page.page_number}: tiles={tile_count}, "
            f"tile={len(raw_detections)}, whole={len(whole_page_detections)}, "
            f"merged={len(merged_detections)} after global NMS"
        )

    result_path = destination / "detections.json"
    result_path.write_text(
        json.dumps(build_output_document(args.source, args, page_results), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Results written to: {result_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
