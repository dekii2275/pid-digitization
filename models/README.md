# Detector checkpoint

`symbol-detector/best.pt` is the existing trained YOLOv8s checkpoint distributed
with this application (22,622,127 bytes). It is tracked so a fresh clone can run
the detector without access to the original workstation. It is a project model,
not the generic COCO checkpoint downloaded by Ultralytics.

SHA-256: `909a7ee65a4cd05afd18cf9b07b0a29c73c991b7bbfc18753fc2e09499cc8d08`.

Other checkpoints, training runs, exported model directories and datasets remain
local and ignored by Git. Replace this file with a retrained checkpoint only
after validating detection and the topology label mapping. The model does not
guarantee detection accuracy on every P&ID drawing.

PaddleOCR downloads its own detection/recognition models on the first pipeline
run. An internet connection is required then; Compose retains the downloaded
models under `artifacts/paddlex-models/` for later runs.
