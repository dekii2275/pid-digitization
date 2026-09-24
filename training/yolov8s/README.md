# YOLOv8 symbol detector

This directory contains the reproducible training, local-preview, and OCR
tooling for the P&ID pipeline. It is independent of the FastAPI service under
`src/` so local model experiments do not mix with production API code.

The repository uses one canonical local environment: `.venv-ocr`. It contains
both PaddleOCR and YOLO/PyTorch dependencies, and should be used for all local
image/PDF inference and detector training commands.

## Rebuild the environment

From the repository root in PowerShell:

```powershell
.\scripts\bootstrap-ocr.ps1
```

The script creates `.venv-ocr`, installs the GPU PaddlePaddle runtime by
default, then installs both `ocr-requirements.txt` and `requirements.txt`.
Use `-PaddleMode cpu` when GPU inference is not needed. The older
`bootstrap-yolov8.ps1` path remains as a compatibility wrapper to the same
unified environment.

On Windows GPU setups, the bootstrap pins the shared cuDNN runtime after both
frameworks are installed. This is required because PaddleOCR/ModelScope loads
PyTorch in the same process and otherwise can fail with a cuDNN `WinError 127`.

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
& .\.venv-ocr\Scripts\python.exe .\training\yolov8s\train_yolov8s.py `
  --dataset-root ..\data\sherifahmed-digitize-pid-yolo\DigitizePID_Dataset `
  --dry-run
```

Train a baseline:

```powershell
& .\.venv-ocr\Scripts\python.exe .\training\yolov8s\train_yolov8s.py `
  --dataset-root ..\data\sherifahmed-digitize-pid-yolo\DigitizePID_Dataset `
  --epochs 100 --imgsz 1280 --batch 4 --device 0
```

Training outputs are written to `artifacts/training/` by default. Copy the
selected checkpoint to `models/symbol-detector/` when you want to retain it.

## Preview one image without labels

```powershell
& .\.venv-ocr\Scripts\python.exe .\training\yolov8s\preview.py `
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
& .\.venv-ocr\Scripts\python.exe .\training\yolov8s\tiled_inference.py `
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

## Text extraction/OCR baseline

`ocr_baseline.py` is the local text stage after symbol detection. It is
independent of the detector and has two input paths:

- A vector/text PDF uses PyMuPDF `get_text("dict")` spans directly. The text
  layer is not rasterized for recognition; its point boxes are mapped to the
  rendered overlay's pixel coordinates.
- An image (or a scanned PDF page without a text layer) uses PaddleOCR with
  `PP-OCRv5_mobile_det` and `en_PP-OCRv5_mobile_rec`. Large images are split
  into overlapping tiles, mapped back to global coordinates, and duplicate
  text boxes are merged before output.

The canonical `.venv-ocr` environment contains the Python 3.13 GPU
PaddlePaddle runtime and the YOLO dependencies. Both the PDF text-only smoke
test and image OCR use this same interpreter:

```powershell
.\scripts\bootstrap-ocr.ps1
```

The bootstrap installs the GPU PaddlePaddle wheel for CUDA 12.6, PyMuPDF,
PaddleOCR, PyTorch, and Ultralytics. Use `-PaddleMode cpu` if GPU runtime is
not needed.

Run it on the checked-in sample PDF (vector text extraction smoke test):

```powershell
& .\.venv-ocr\Scripts\python.exe .\training\yolov8s\ocr_baseline.py `
  --source .\..\data\check\8474L-015-PID-0021-121.pdf `
  --output-dir .\artifacts\ocr-baseline\sample-pdf `
  --dpi 150 --no-pdf-ocr-fallback
```

Run the raster PaddleOCR branch on the checked-in sample image:

```powershell
& .\.venv-ocr\Scripts\python.exe .\training\yolov8s\ocr_baseline.py `
  --source .\..\data\check\anhcheck1.jpg `
  --tile-size 2048 --overlap 0.20 --device gpu:0
```

Both commands write `ocr.json` and a full-size `page-001_overlay.png` below
the output directory. Each item in `pages[].texts[]` has the common
`id`, `text`, `bbox`, `confidence`, and `source` fields. `source` is
`pdf_text` for direct PDF text-layer extraction or `ocr` for PaddleOCR.
The boxes are already in the same global pixel coordinate system as symbol
detections, so a future line detector can build a mask from both outputs.

## Line detection baseline

`line_detection_baseline.py` is the next local stage. It consumes the global
`bbox` values from `detections.json` and `ocr.json`, masks those regions on the
full source page, binarizes the remaining drawing, applies Zhang-Suen thinning,
traverses skeleton rows/columns for horizontal/vertical lines, and uses
`HoughLinesP` for diagonal lines. Same-direction, near-collinear fragments are
merged and shorter than `--min-line-length` are removed. The resulting
coordinates remain global source-image pixels.

Smoke test using the checked-in symbol and OCR artifacts:

```powershell
& .\.venv-ocr\Scripts\python.exe .\training\yolov8s\line_detection_baseline.py `
  --source .\..\data\check\anhcheck1.jpg `
  --symbols .\artifacts\tiled-inference\anhcheck1\detections.json `
  --texts .\artifacts\ocr-baseline\anhcheck1\ocr.json `
  --output-dir .\artifacts\line-detection\anhcheck1
```

The command writes `lines.json`, `page-001_line_overlay.png`, and the masked,
binary, and thinned debug images. The image JSON has this shape:

```json
{
  "lines": [
    {
      "id": "line_001",
      "start": [120, 500],
      "end": [900, 500],
      "orientation": "horizontal"
    }
  ]
}
```

Useful configurable parameters are `--threshold`, `--binary-threshold`,
`--min-line-length`, `--merge-gap`, `--merge-distance`, and
`--angle-tolerance`. `--no-thinning` is available for comparison runs. The
default `--binary-threshold 0` selects Otsu thresholding; a fixed threshold
can be supplied when scan illumination is uneven.

## End-to-end topology reconstruction

`run_pid_pipeline.py` connects the three local inference stages to the existing
legacy `graph_construction_service.construct_graph()` implementation. The
adapter converts pixel coordinates to the normalized Pydantic models expected
by the legacy module, reuses its symbol/text correlation, and leaves the
topology algorithm unchanged.

Run the complete pipeline on an image:

```powershell
& .\.venv-ocr\Scripts\python.exe .\training\yolov8s\run_pid_pipeline.py `
  --source .\..\data\check\anhcheck1.jpg `
  --output-dir .\artifacts\pid-pipeline\anhcheck1 `
  --device 0 --ocr-device gpu:0
```

To rerun only the topology integration with existing stage artifacts:

```powershell
& .\.venv-ocr\Scripts\python.exe .\training\yolov8s\run_pid_pipeline.py `
  --source .\..\data\check\anhcheck1.jpg `
  --symbols-json .\artifacts\tiled-inference\anhcheck1\detections.json `
  --texts-json .\artifacts\ocr-baseline\anhcheck1\ocr.json `
  --lines-json .\artifacts\line-detection\anhcheck1\lines.json `
  --output-dir .\artifacts\topology\anhcheck1
```

The topology output contains `connectivity.json`, `graph_network.png`,
`graph_connections_overlay.png`, `graph_lines_symbols.png`, and
`adapter_report.json`. The report records input counts, label mappings,
coordinate assumptions, and any unmapped detector labels.

### Editable drawing MVP

Add `--build-editor` to create `editor/scene.json`, a copied background image,
and a local SVG editor. The editor renders the detector/OCR/line outputs as
separate objects, so symbols, text, and line endpoints can be moved and saved
without modifying the legacy graph implementation.

```powershell
& .\.venv-ocr\Scripts\python.exe .\training\yolov8s\run_pid_pipeline.py `
  --source .\..\data\check\anhcheck1.jpg `
  --output-dir .\artifacts\pid-pipeline\anhcheck1 `
  --device 0 --ocr-device gpu:0 --build-editor
```

Serve the generated editor folder and open `http://127.0.0.1:8765/`:

```powershell
python -m http.server 8765 --directory .\artifacts\pid-pipeline\anhcheck1\editor
```

The MVP supports layer toggles, zoom, selection, drag-and-drop, line endpoint
handles, OCR text editing, adding/deleting objects, JSON save, and SVG export.
