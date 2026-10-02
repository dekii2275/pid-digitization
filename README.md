# P&ID Digitization

This repository is a foundation for converting P&ID/PFD images into structured
engineering data: symbol detections, OCR text, line segments, and a connection
graph. The repository currently contains both the original FastAPI/graph
service and a local YOLOv8 symbol-detector workflow.

## Start here

- [Project layout and rebuild boundaries](docs/project-layout.md)
- [YOLOv8 training and preview workflow](training/yolov8s/README.md)
- [Local OCR/text extraction baseline](training/yolov8s/README.md#text-extractionocr-baseline)
- [API source and local run instructions](src/README.md)
- [Target MVP pipeline](docs/pipeline.md)
- [Plan for a self-hosted/open-source rebuild](docs/open-source-rebuild-plan.md)
- [Docker deployment guide](DEPLOYMENT.md)

## Quick start

### Run the drawing review app

The default Docker Compose profile starts the React UI and the FastAPI drawing
service. Uploaded files and generated previews are stored in local bind mounts.

```powershell
docker compose up --build -d
```

Open `http://localhost:18731` for the UI or `http://localhost:18732/docs`
for the API. Stop the services with `docker compose down`.

The legacy worker, PostgreSQL, and Redis services are available under the
`full-stack` profile:

```powershell
docker compose --profile full-stack up --build -d
```

The repository contains two complementary workflows:

- **Application stack:** FastAPI API, worker, PostgreSQL, Redis, and React UI.
- **Local ML pipeline:** symbol detection, OCR, line detection, and topology
  reconstruction from a P&ID/PFD image or PDF.

For the `full-stack` profile, copy `.env.docker.example` to `.env` and set a
unique database password before deploying outside a local development machine.

### Run the local ML pipeline

```powershell
.\scripts\bootstrap-ocr.ps1
& .\.venv-ocr\Scripts\python.exe .\training\yolov8s\run_pid_pipeline.py `
  --source ..\data\check\anhcheck1.jpg `
  --output-dir .\artifacts\pid-pipeline\anhcheck1
```

See [`training/yolov8s/README.md`](training/yolov8s/README.md) for model
weights, OCR options, and stage-by-stage commands.

## Before pushing to GitHub

Commit source code, tests, configuration examples, and documentation. Do not
commit `.env`, model weights, uploads, generated artifacts, virtual
environments, or generated deliverables. This repository's `.gitignore`
enforces those boundaries.

```powershell
git status
git add .
git diff --cached --check
git commit -m "Describe your change"
```

The configured `origin` points to the project repository, while `upstream`
points to Azure Samples. Push your branch to `origin`:

```powershell
git push origin main
```

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
