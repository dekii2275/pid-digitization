"""Render YOLO detections as bounding boxes without class names or scores."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = REPOSITORY_ROOT / "artifacts" / "predictions"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weights", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--imgsz", type=int, default=1280)
    parser.add_argument("--conf", type=float, default=0.10)
    parser.add_argument("--iou", type=float, default=0.70)
    parser.add_argument("--device", default=None, help="For example: 0, cpu, or cuda:0.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.weights.is_file():
        raise FileNotFoundError(f"Weights not found: {args.weights}")
    if not args.source.exists():
        raise FileNotFoundError(f"Source not found: {args.source}")

    try:
        import cv2
        from ultralytics import YOLO
    except ImportError as exc:
        raise RuntimeError(
            "YOLO dependencies are missing. Run .\\scripts\\bootstrap-yolov8.ps1 first."
        ) from exc

    output_dir = args.output_dir / f"{args.source.stem}-boxes"
    output_dir.mkdir(parents=True, exist_ok=True)
    model = YOLO(str(args.weights))
    results = model.predict(
        source=str(args.source),
        imgsz=args.imgsz,
        conf=args.conf,
        iou=args.iou,
        device=args.device,
        save=False,
        verbose=True,
    )

    for result in results:
        rendered = result.plot(labels=False, conf=False)
        output_path = output_dir / Path(result.path).name
        if not cv2.imwrite(str(output_path), rendered):
            raise RuntimeError(f"Could not write preview: {output_path}")
        print(f"Preview written to: {output_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
