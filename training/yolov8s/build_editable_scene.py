"""Build an editable scene JSON and local SVG editor from pipeline outputs.

This is a presentation/editor layer. It does not replace the legacy topology
algorithm; it preserves detector, OCR, line, and legacy connectivity records
as editable scene objects.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
EDITOR_TEMPLATE = SCRIPT_DIR / "interactive_pid_editor.html"


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _page(document: Any, page_number: int) -> dict[str, Any]:
    pages = document.get("pages") if isinstance(document, dict) else None
    if isinstance(pages, list):
        for page in pages:
            if isinstance(page, dict) and page.get("page_number") == page_number:
                return page
        raise ValueError(f"Page {page_number} is not present")
    if isinstance(document, dict):
        return document
    raise ValueError("Expected a JSON object")


def _bbox(item: dict[str, Any]) -> tuple[float, float, float, float]:
    values = item.get("bbox")
    if not isinstance(values, (list, tuple)) or len(values) != 4:
        raise ValueError(f"Invalid bbox: {item!r}")
    x1, y1, x2, y2 = (float(value) for value in values)
    return x1, y1, max(0.5, x2 - x1), max(0.5, y2 - y1)


def _build_symbols(payload: dict[str, Any]) -> list[dict[str, Any]]:
    symbols = []
    for index, item in enumerate(payload.get("detections", [])):
        if not isinstance(item, dict):
            continue
        try:
            x, y, width, height = _bbox(item)
        except (TypeError, ValueError):
            continue
        symbols.append(
            {
                "id": f"s-{index}",
                "index": index,
                "type": str(item.get("class_name", "Unknown")),
                "class_id": item.get("class_id"),
                "confidence": item.get("confidence"),
                "x": x,
                "y": y,
                "width": width,
                "height": height,
                "rotation": 0,
            }
        )
    return symbols


def _build_texts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    texts = []
    for index, item in enumerate(payload.get("texts", [])):
        if not isinstance(item, dict):
            continue
        text = " ".join(str(item.get("text", "")).split()).strip()
        if not text:
            continue
        try:
            x, y, width, height = _bbox(item)
        except (TypeError, ValueError):
            continue
        texts.append(
            {
                "id": str(item.get("id", f"text-{index:04d}")),
                "text": text,
                "confidence": item.get("confidence"),
                "source": item.get("source", "ocr"),
                "x": x,
                "y": y,
                "width": width,
                "height": height,
            }
        )
    return texts


def _build_lines(payload: dict[str, Any]) -> list[dict[str, Any]]:
    lines = []
    for index, item in enumerate(payload.get("lines", [])):
        if not isinstance(item, dict):
            continue
        start = item.get("start")
        end = item.get("end")
        if not isinstance(start, (list, tuple)) or not isinstance(end, (list, tuple)):
            continue
        if len(start) != 2 or len(end) != 2:
            continue
        lines.append(
            {
                "id": str(item.get("id", f"line-{index:04d}")),
                "x1": float(start[0]),
                "y1": float(start[1]),
                "x2": float(end[0]),
                "y2": float(end[1]),
                "orientation": item.get("orientation", "unknown"),
            }
        )
    return lines


def _build_topology_edges(connectivity: dict[str, Any]) -> list[dict[str, Any]]:
    edges = []
    seen: set[tuple[str, str]] = set()
    for source in connectivity.get("connected_symbols", []):
        if not isinstance(source, dict):
            continue
        source_id = f"s-{source.get('id')}"
        for target in source.get("connections", []):
            if not isinstance(target, dict):
                continue
            target_id = f"s-{target.get('id')}"
            if source_id == "s-None" or target_id == "s-None" or source_id == target_id:
                continue
            key = tuple(sorted((source_id, target_id)))
            if key in seen:
                continue
            seen.add(key)
            edges.append(
                {
                    "id": f"edge-{len(edges):04d}",
                    "source": source_id,
                    "target": target_id,
                    "flow_direction": target.get("flow_direction", "unknown"),
                    "segments": target.get("segments", []),
                }
            )
    return edges


def build_scene(
    source: Path,
    symbols_path: Path,
    texts_path: Path,
    lines_path: Path,
    connectivity_path: Path,
    output_dir: Path,
    page_number: int = 1,
) -> Path:
    symbols_document = _load(symbols_path)
    texts_document = _load(texts_path)
    lines_document = _load(lines_path)
    connectivity = _load(connectivity_path)
    symbols_payload = _page(symbols_document, page_number)
    texts_payload = _page(texts_document, page_number)
    lines_payload = _page(lines_document, page_number)
    image_size = symbols_payload.get("image_size") or texts_payload.get("image_size")
    if not isinstance(image_size, dict):
        raise ValueError("Could not determine image size")

    output_dir.mkdir(parents=True, exist_ok=True)
    background_name = f"background{source.suffix.lower() or '.jpg'}"
    shutil.copy2(source, output_dir / background_name)
    shutil.copy2(EDITOR_TEMPLATE, output_dir / "index.html")

    scene = {
        "schema_version": "0.1",
        "source": {
            "name": source.name,
            "width": int(image_size["width"]),
            "height": int(image_size["height"]),
            "background": background_name,
        },
        "symbols": _build_symbols(symbols_payload),
        "texts": _build_texts(texts_payload),
        "lines": _build_lines(lines_payload),
        "topology_edges": _build_topology_edges(connectivity),
        "metadata": {
            "symbols_input": str(symbols_path.resolve()),
            "texts_input": str(texts_path.resolve()),
            "lines_input": str(lines_path.resolve()),
            "connectivity_input": str(connectivity_path.resolve()),
            "note": "Initial scene is detector/OCR/line data. Edits are stored in this scene JSON.",
        },
    }
    scene_path = output_dir / "scene.json"
    scene_path.write_text(json.dumps(scene, ensure_ascii=False, indent=2), encoding="utf-8")
    return scene_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--symbols", required=True, type=Path)
    parser.add_argument("--texts", required=True, type=Path)
    parser.add_argument("--lines", required=True, type=Path)
    parser.add_argument("--connectivity", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--page-number", type=int, default=1)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    for path in (args.source, args.symbols, args.texts, args.lines, args.connectivity, EDITOR_TEMPLATE):
        if not path.is_file():
            raise FileNotFoundError(path)
    scene_path = build_scene(
        source=args.source,
        symbols_path=args.symbols,
        texts_path=args.texts,
        lines_path=args.lines,
        connectivity_path=args.connectivity,
        output_dir=args.output_dir,
        page_number=args.page_number,
    )
    print(f"Editable scene: {scene_path.resolve()}")
    print(f"Editor: {(args.output_dir / 'index.html').resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
