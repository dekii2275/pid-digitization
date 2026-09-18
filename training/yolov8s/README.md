# YOLOv8 symbol detector

This directory contains the reproducible training and local-preview tooling
for the P&ID symbol detector. It is independent of the FastAPI service under
`src/` so model experiments do not mix with production API code.

## Rebuild the environment

From the repository root in PowerShell:

```powershell
.\scripts\bootstrap-yolov8.ps1
```

The script creates `.venv-yolov8s` and installs the pinned dependencies in
`requirements.txt`.

## Validate data and train

The dataset remains outside the repository. Its expected layout is:

```text
<dataset-root>/
  images/train/
  images/val/
  labels/train/
  labels/val/
```

Validate annotations without training:

```powershell
& .\.venv-yolov8s\Scripts\python.exe .\training\yolov8s\train_yolov8s.py `
  --dataset-root ..\data\sherifahmed-digitize-pid-yolo\DigitizePID_Dataset `
  --dry-run
```

Train a baseline:

```powershell
& .\.venv-yolov8s\Scripts\python.exe .\training\yolov8s\train_yolov8s.py `
  --dataset-root ..\data\sherifahmed-digitize-pid-yolo\DigitizePID_Dataset `
  --epochs 100 --imgsz 1280 --batch 4 --device 0
```

Training outputs are written to `artifacts/training/` by default. Copy the
selected checkpoint to `models/symbol-detector/` when you want to retain it.

## Preview one image without labels

```powershell
& .\.venv-yolov8s\Scripts\python.exe .\training\yolov8s\preview.py `
  --weights .\models\symbol-detector\best.pt `
  --source ..\data\check\anhcheck1.jpg `
  --imgsz 1280 --conf 0.10
```

The preview image contains bounding boxes only and is written below
`artifacts/predictions/`.

## Tiled inference baseline

`tiled_inference.py` supports source images and PDFs. PDFs are rendered at
600 DPI by default. It uses two complementary branches: an unchanged full-page
pass (which preserves the scale/context at which this checkpoint recognizes
round and diamond instrument symbols) and 1024x1024 tiles with a 25% overlap
(a 768-pixel stride) for smaller symbols. Both branches are mapped to global
coordinates and merged with class-aware NMS.

```powershell
& .\.venv-yolov8s\Scripts\python.exe .\training\yolov8s\tiled_inference.py `
  --source ..\data\check\8474L-015-PID-0021-121.pdf `
  --weights .\models\symbol-detector\best.pt `
  --device 0
```

Defaults are `dpi=600`, `tile-size=1024`, `overlap=0.25`, `imgsz=1024`,
`conf=0.15`, global `iou=0.50`, plus a full-page pass at `whole-imgsz=1280`
and `whole-conf=0.10`. To avoid detecting the technical/title panel, the
default retained region is `0,0,0.80,1.0` (the left 80% of the page). Use
`--content-region 0,0,1,1` to disable that filter, or `--no-whole-image` to
run tiles only. Every option is configurable from the CLI.
The command writes one full-size unlabeled overlay per page and a
`detections.json` document below `artifacts/tiled-inference/<source-stem>/`.
Each detection contains `class_id`, `class_name`, `confidence`, `bbox` as
`[x1, y1, x2, y2]`, and `center`, all in original-image pixel coordinates.
