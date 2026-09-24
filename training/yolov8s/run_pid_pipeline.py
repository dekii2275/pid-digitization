"""Run the local P&ID pipeline through legacy topology reconstruction.

Pipeline:

    tiled YOLO symbols + OCR text + geometric line detection
        -> topology_adapter.py
        -> legacy construct_graph()
        -> connectivity JSON + graph debug images

Existing stage JSON can be supplied with ``--symbols-json``, ``--texts-json``
and ``--lines-json`` to rerun only the adapter/topology step.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = SCRIPT_DIR.parents[1]
DEFAULT_WEIGHTS = REPOSITORY_ROOT / "models" / "symbol-detector" / "best.pt"


def _run_stage(command: list[str]) -> None:
    print("+", " ".join(f'"{part}"' if " " in part else part for part in command))
    subprocess.run(command, cwd=SCRIPT_DIR, check=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--weights", type=Path, default=DEFAULT_WEIGHTS)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--device", default=None, help="YOLO device, for example cpu or 0")
    parser.add_argument("--ocr-device", default="cpu")
    parser.add_argument("--dpi", type=int, default=600)
    parser.add_argument("--pages", default="all")
    parser.add_argument("--tile-size", type=int, default=1024)
    parser.add_argument("--overlap", type=float, default=0.25)
    parser.add_argument("--imgsz", type=int, default=1024)
    parser.add_argument("--conf", type=float, default=0.15)
    parser.add_argument("--line-min-length", type=float, default=30.0)
    parser.add_argument("--line-merge-gap", type=float, default=12.0)
    parser.add_argument("--page-number", type=int, default=1)
    parser.add_argument("--symbols-json", type=Path, default=None)
    parser.add_argument("--texts-json", type=Path, default=None)
    parser.add_argument("--lines-json", type=Path, default=None)
    parser.add_argument("--association-area-threshold", type=float, default=0.8)
    parser.add_argument("--association-distance-threshold", type=float, default=0.01)
    parser.add_argument("--propagation-pass-exhaustive-search", action="store_true")
    parser.add_argument(
        "--build-editor",
        action="store_true",
        help="Build an editable SVG scene and local editor after topology reconstruction",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source = args.source.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if source.suffix.lower() == ".pdf":
        raise ValueError(
            "The adapter currently consumes a rendered raster page. Run the stages "
            "for a selected PDF page and pass that rendered page image to the adapter."
        )

    output_dir = (args.output_dir or REPOSITORY_ROOT / "artifacts" / "pid-pipeline" / source.stem).resolve()
    symbols_dir = output_dir / "symbols"
    texts_dir = output_dir / "ocr"
    lines_dir = output_dir / "lines"
    topology_dir = output_dir / "topology"
    output_dir.mkdir(parents=True, exist_ok=True)

    symbols_json = args.symbols_json.resolve() if args.symbols_json else symbols_dir / "detections.json"
    texts_json = args.texts_json.resolve() if args.texts_json else texts_dir / "ocr.json"
    lines_json = args.lines_json.resolve() if args.lines_json else lines_dir / "lines.json"

    if args.symbols_json is None:
        command = [
            sys.executable,
            str(SCRIPT_DIR / "tiled_inference.py"),
            "--source",
            str(source),
            "--weights",
            str(args.weights.resolve()),
            "--output-dir",
            str(symbols_dir),
            "--dpi",
            str(args.dpi),
            "--pages",
            args.pages,
            "--tile-size",
            str(args.tile_size),
            "--overlap",
            str(args.overlap),
            "--imgsz",
            str(args.imgsz),
            "--conf",
            str(args.conf),
        ]
        if args.device:
            command.extend(["--device", args.device])
        _run_stage(command)

    if args.texts_json is None:
        command = [
            sys.executable,
            str(SCRIPT_DIR / "ocr_baseline.py"),
            "--source",
            str(source),
            "--output-dir",
            str(texts_dir),
            "--dpi",
            str(args.dpi),
            "--pages",
            args.pages,
            "--device",
            args.ocr_device,
        ]
        _run_stage(command)

    if args.lines_json is None:
        _run_stage(
            [
                sys.executable,
                str(SCRIPT_DIR / "line_detection_baseline.py"),
                "--source",
                str(source),
                "--symbols",
                str(symbols_json),
                "--texts",
                str(texts_json),
                "--output-dir",
                str(lines_dir),
                "--dpi",
                str(args.dpi),
                "--pages",
                args.pages,
                "--min-line-length",
                str(args.line_min_length),
                "--merge-gap",
                str(args.line_merge_gap),
            ]
        )

    for path in (symbols_json, texts_json, lines_json):
        if not path.is_file():
            raise FileNotFoundError(f"Expected stage output was not found: {path}")

    adapter_command = [
        sys.executable,
        str(SCRIPT_DIR / "topology_adapter.py"),
        "--source",
        str(source),
        "--symbols",
        str(symbols_json),
        "--texts",
        str(texts_json),
        "--lines",
        str(lines_json),
        "--output-dir",
        str(topology_dir),
        "--page-number",
        str(args.page_number),
        "--association-area-threshold",
        str(args.association_area_threshold),
        "--association-distance-threshold",
        str(args.association_distance_threshold),
    ]
    if args.propagation_pass_exhaustive_search:
        adapter_command.append("--propagation-pass-exhaustive-search")
    _run_stage(adapter_command)
    if args.build_editor:
        _run_stage(
            [
                sys.executable,
                str(SCRIPT_DIR / "build_editable_scene.py"),
                "--source",
                str(source),
                "--symbols",
                str(symbols_json),
                "--texts",
                str(texts_json),
                "--lines",
                str(lines_json),
                "--connectivity",
                str(topology_dir / "connectivity.json"),
                "--output-dir",
                str(output_dir / "editor"),
                "--page-number",
                str(args.page_number),
            ]
        )
    print(f"Pipeline complete: {topology_dir}")
    if args.build_editor:
        print(f"Editable editor: {output_dir / 'editor' / 'index.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
