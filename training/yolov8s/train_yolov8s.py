"""Train or fine-tune a YOLOv8-small detector on the Digitize-PID dataset.

The script is intentionally independent from the inference service. It accepts
the dataset root containing images/{train,val} and labels/{train,val},
validates the YOLO annotations, writes a dataset YAML, and then launches an
Ultralytics YOLOv8 detection training run.

Examples
--------
Local smoke test:

    python train_yolov8s.py --dataset-root ../../../data/sherifahmed-digitize-pid-yolo/DigitizePID_Dataset --epochs 5 --imgsz 1024 --batch 2 --dry-run

Local training:

    python train_yolov8s.py --dataset-root ../../../data/sherifahmed-digitize-pid-yolo/DigitizePID_Dataset --epochs 100 --imgsz 1280 --batch 4 --device 0

Fine-tuning an existing checkpoint is supported by passing its path to
--model instead of yolov8s.pt.
"""

from __future__ import annotations

import argparse
import warnings
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from class_names import CLASS_NAMES

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
SPLITS = ("train", "val")
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROJECT_DIR = REPOSITORY_ROOT / "artifacts" / "training"
LOCAL_BASE_MODEL = REPOSITORY_ROOT / "models" / "pretrained" / "yolov8s.pt"


def is_dataset_root(path: Path) -> bool:
    """Return whether path has the expected YOLO directory layout."""

    return all(
        (path / "images" / split).is_dir()
        and (path / "labels" / split).is_dir()
        for split in SPLITS
    )


def resolve_dataset_root(explicit_root: Optional[str]) -> Path:
    """Resolve a local or Kaggle dataset root."""

    candidates: List[Path] = []
    if explicit_root:
        candidates.append(Path(explicit_root).expanduser())
    else:
        here = Path(__file__).resolve()
        workspace_root = here.parents[3] if len(here.parents) > 3 else here.parent
        candidates.extend(
            [
                Path.cwd(),
                workspace_root
                / "data"
                / "sherifahmed-digitize-pid-yolo"
                / "DigitizePID_Dataset",
                workspace_root / "data" / "sherifahmed-digitize-pid-yolo",
                Path("/kaggle/input"),
            ]
        )

    for candidate in candidates:
        candidate = candidate.resolve()
        if is_dataset_root(candidate):
            return candidate
        nested = candidate / "DigitizePID_Dataset"
        if is_dataset_root(nested):
            return nested

    for base in candidates:
        base = base.resolve()
        if not base.is_dir():
            continue
        try:
            for images_train in base.rglob("images/train"):
                root = images_train.parent.parent
                if is_dataset_root(root):
                    return root
        except OSError:
            continue

    searched = "\n".join(f"  - {path}" for path in candidates)
    raise FileNotFoundError(
        "Could not find a YOLO dataset root. Expected images/{train,val} and "
        f"labels/{{train,val}}. Searched:\n{searched}"
    )


def image_files(directory: Path) -> List[Path]:
    return sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )


def validate_split(root: Path, split: str) -> Dict[str, object]:
    """Validate one YOLO split and return compact statistics."""

    images_dir = root / "images" / split
    labels_dir = root / "labels" / split
    images = image_files(images_dir)
    image_stems = {image.stem for image in images}
    label_files = sorted(labels_dir.glob("*.txt"))
    label_stems = {label.stem for label in label_files}

    missing_labels = sorted(image_stems - label_stems)
    orphan_labels = sorted(label_stems - image_stems)
    if missing_labels:
        warnings.warn(
            f"{split}: {len(missing_labels)} image(s) have no matching label file. "
            "Empty-label images are valid, but verify this is intentional."
        )
    if orphan_labels:
        warnings.warn(f"{split}: {len(orphan_labels)} label file(s) have no image.")

    class_counts: Counter = Counter()
    box_count = 0
    errors: List[str] = []
    for label_file in label_files:
        try:
            lines = label_file.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError as exc:
            errors.append(f"{label_file}: not UTF-8 ({exc})")
            continue

        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            fields = line.split()
            if len(fields) != 5:
                errors.append(
                    f"{label_file}:{line_number}: expected 5 fields, got {len(fields)}"
                )
                continue
            try:
                class_id = int(fields[0])
                x_center, y_center, width, height = (
                    float(value) for value in fields[1:]
                )
            except ValueError as exc:
                errors.append(f"{label_file}:{line_number}: invalid numeric value ({exc})")
                continue

            values = (x_center, y_center, width, height)
            if not all(0.0 <= value <= 1.0 for value in values):
                errors.append(
                    f"{label_file}:{line_number}: coordinates must be in [0, 1], got {values}"
                )
            if width <= 0.0 or height <= 0.0:
                errors.append(f"{label_file}:{line_number}: width and height must be positive")
            if class_id < 0 or class_id >= len(CLASS_NAMES):
                errors.append(
                    f"{label_file}:{line_number}: class id {class_id} is outside "
                    f"[0, {len(CLASS_NAMES) - 1}]"
                )

            class_counts[class_id] += 1
            box_count += 1

    if errors:
        preview = "\n".join(f"  - {error}" for error in errors[:20])
        extra = "" if len(errors) <= 20 else f"\n  - ... and {len(errors) - 20} more"
        raise ValueError(f"Invalid {split} annotations:\n{preview}{extra}")

    return {
        "images": len(images),
        "label_files": len(label_files),
        "boxes": box_count,
        "classes_present": sorted(class_counts),
        "missing_labels": len(missing_labels),
        "orphan_labels": len(orphan_labels),
        "class_counts": dict(sorted(class_counts.items())),
    }


def validate_dataset(root: Path) -> Dict[str, Dict[str, object]]:
    stats = {split: validate_split(root, split) for split in SPLITS}
    all_classes = set()
    for split_stats in stats.values():
        all_classes.update(split_stats["classes_present"])
    missing_classes = sorted(set(range(len(CLASS_NAMES))) - all_classes)
    if missing_classes:
        warnings.warn(f"Classes absent from both splits: {missing_classes}")
    return stats


def yaml_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def write_dataset_yaml(root: Path, output_dir: Path) -> Path:
    """Write an Ultralytics-compatible YAML without requiring PyYAML."""

    output_dir.mkdir(parents=True, exist_ok=True)
    yaml_path = output_dir / "digitize_pid_yolov8s.yaml"
    lines = [
        f"path: {yaml_quote(root.resolve().as_posix())}",
        "train: images/train",
        "val: images/val",
        f"nc: {len(CLASS_NAMES)}",
        "names:",
    ]
    lines.extend(f"  - {yaml_quote(name)}" for name in CLASS_NAMES)
    yaml_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return yaml_path


def print_summary(
    root: Path, stats: Dict[str, Dict[str, object]], yaml_path: Path
) -> None:
    print(f"Dataset root: {root}")
    print(f"Dataset YAML: {yaml_path}")
    print(f"Classes: {len(CLASS_NAMES)}")
    for split, split_stats in stats.items():
        print(
            f"{split}: images={split_stats['images']}, "
            f"labels={split_stats['label_files']}, boxes={split_stats['boxes']}"
        )
    print("Class counts:")
    combined: Counter = Counter()
    for split_stats in stats.values():
        combined.update(split_stats["class_counts"])
    for class_id, name in enumerate(CLASS_NAMES):
        print(f"  {class_id:02d} {combined[class_id]:6d}  {name}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    default_model = str(LOCAL_BASE_MODEL) if LOCAL_BASE_MODEL.is_file() else "yolov8s.pt"
    parser.add_argument(
        "--dataset-root",
        default=None,
        help="Directory containing images/{train,val} and labels/{train,val}.",
    )
    parser.add_argument(
        "--model",
        default=default_model,
        help=(
            "Pretrained or existing checkpoint. Uses models/pretrained/yolov8s.pt "
            "when available, otherwise lets Ultralytics obtain yolov8s.pt."
        ),
    )
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--imgsz", type=int, default=1280)
    parser.add_argument("--batch", type=int, default=4)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--device", default="auto", help="auto, cpu, 0, 0,1, ...")
    parser.add_argument(
        "--project",
        default=str(DEFAULT_PROJECT_DIR),
        help="Directory for generated training artifacts.",
    )
    parser.add_argument("--name", default="digitize-pid-yolov8s")
    parser.add_argument("--patience", type=int, default=25)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument(
        "--cache",
        choices=("false", "ram", "disk"),
        default="false",
        help="Ultralytics image cache mode.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate annotations and write YAML without training.",
    )
    return parser


def resolve_device(requested: str) -> object:
    if requested.lower() != "auto":
        return requested
    try:
        import torch

        return 0 if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"


def train(args: argparse.Namespace, data_yaml: Path) -> None:
    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise RuntimeError(
            "Ultralytics is not installed. Install it with "
            "'pip install ultralytics' or run the Kaggle notebook."
        ) from exc

    device = resolve_device(args.device)
    cache: object = False if args.cache == "false" else args.cache
    print(f"Starting YOLOv8s training on device={device} ...")
    model = YOLO(args.model)
    model.train(
        data=str(data_yaml),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        workers=args.workers,
        device=device,
        project=args.project,
        name=args.name,
        patience=args.patience,
        seed=args.seed,
        cache=cache,
        pretrained=True,
        plots=True,
        exist_ok=True,
    )

    best_path = Path(args.project) / args.name / "weights" / "best.pt"
    if not best_path.exists():
        warnings.warn(f"Training finished but best checkpoint was not found at {best_path}")
        return

    print(f"Best checkpoint: {best_path.resolve()}")
    best_model = YOLO(str(best_path))
    metrics = best_model.val(
        data=str(data_yaml),
        imgsz=args.imgsz,
        batch=args.batch,
        device=device,
        workers=args.workers,
        plots=True,
    )
    print(f"Validation mAP50-95: {metrics.box.map:.4f}")
    print(f"Validation mAP50: {metrics.box.map50:.4f}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    dataset_root = resolve_dataset_root(args.dataset_root)
    stats = validate_dataset(dataset_root)

    if args.output_dir:
        yaml_output_dir = Path(args.output_dir)
    else:
        yaml_output_dir = Path(args.project) / args.name
    data_yaml = write_dataset_yaml(dataset_root, yaml_output_dir)
    print_summary(dataset_root, stats, data_yaml)

    if args.dry_run:
        print("Dry run complete; training was not started.")
        return 0

    train(args, data_yaml)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
