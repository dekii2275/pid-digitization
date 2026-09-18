# P&ID Digitization

This repository is a foundation for converting P&ID/PFD images into structured
engineering data: symbol detections, OCR text, line segments, and a connection
graph. The repository currently contains both the original FastAPI/graph
service and a local YOLOv8 symbol-detector workflow.

## Start here

- [Project layout and rebuild boundaries](docs/project-layout.md)
- [YOLOv8 training and preview workflow](training/yolov8s/README.md)
- [API source and local run instructions](src/README.md)
- [Target MVP pipeline](docs/pipeline.md)
- [Plan for a self-hosted/open-source rebuild](docs/open-source-rebuild-plan.md)

## Repository layout

```text
src/             FastAPI service, topology/graph code, database model, tests
training/        Reproducible detector training and local inference tools
scripts/         Environment bootstrap scripts
notebooks/       Experiment notebooks
models/          Local model weights (not committed)
artifacts/       Generated training and prediction outputs (not committed)
docs/            Architecture and operational documentation
```

## What is versioned

Source code, tests, dependency specifications, documentation, and bootstrap
scripts belong in Git. Datasets, PDFs, virtual environments, checkpoints, and
generated outputs do not; put them in the documented local locations instead.

## Current architecture note

The original FastAPI service keeps its external symbol-detection and Azure
integration contracts. The local YOLOv8 workflow is available for model
experimentation and visual validation, but it is not yet wired into the API.
This separation keeps the existing service stable while the local rebuild is
implemented incrementally.
