# P&ID Digitization

This repository is a foundation for converting P&ID/PFD images into structured
engineering data: symbol detections, OCR text, line segments, and a connection
graph. The repository currently contains both the original FastAPI/graph
service and a local YOLOv8 symbol-detector workflow. The default application is
`app.web_main`, with React, PostgreSQL and the local CPU AI pipeline.

## Start here

- [Project layout and rebuild boundaries](docs/project-layout.md)
- [YOLOv8 training and preview workflow](training/yolov8s/README.md)
- [Local OCR/text extraction baseline](training/yolov8s/README.md#text-extractionocr-baseline)
- [API source and local run instructions](src/README.md)
- [Target MVP pipeline](docs/pipeline.md)
- [Plan for a self-hosted/open-source rebuild](docs/open-source-rebuild-plan.md)
- [Docker deployment guide](DEPLOYMENT.md)
- [Symbol catalog storage and web import](docs/symbol_library.md)
- [Code style and source validation](docs/code-style.md)

## Quick start

### Run the drawing review app

The default Docker Compose profile starts the React UI, FastAPI drawing service,
PostgreSQL and MinIO. Original drawing files are stored in MinIO; drawing metadata,
manual annotations and the reviewed symbol catalog are stored in PostgreSQL.
Generated previews and tiles use local caches. The **Data** tab manages uploads,
deletions, drawing lists and saved labels; see [drawing management](docs/data.md).

```powershell
Copy-Item .env.docker.example .env  # only if .env does not exist
docker compose up --build -d --wait --wait-timeout 180
```

Open `http://localhost:18731` for the UI or `http://localhost:18732/docs`
for the API. Stop the services with `docker compose down`. Use Docker Desktop
with Linux containers on x86-64; no host Python, Node.js or GPU is required.
The first build downloads AI dependencies. The trained detector checkpoint is
bundled; PaddleOCR downloads and caches its models on the first pipeline run.
Python runtime dependencies are pinned in `src/constraints.web.txt`; frontend
dependencies use `frontend/package-lock.json`.

The legacy worker and Redis services are available under the `full-stack`
profile for development of `app.main`; they do not consume review API jobs:

```powershell
docker compose --profile full-stack up --build -d
```

The repository contains two complementary workflows:

- **Application stack:** FastAPI API, worker, PostgreSQL, Redis, and React UI.
- **Local ML pipeline:** symbol detection, OCR, line detection, and topology
  reconstruction from a P&ID/PFD image or PDF.

For every profile, copy `.env.docker.example` to `.env` and set a
unique database and MinIO passwords before deploying outside a local development machine.

### Run the local ML pipeline

```powershell
.\scripts\bootstrap-ocr.ps1
& .\.venv-ocr\Scripts\python.exe .\training\yolov8s\run_pid_pipeline.py `
  --source .\src\app\seed_symbols\PNG.png `
  --output-dir .\artifacts\pid-pipeline\example
```

See [`training/yolov8s/README.md`](training/yolov8s/README.md) for model
weights, OCR options, and stage-by-stage commands.

## Before pushing to GitHub

Commit source code, tests, configuration examples, and documentation. Do not
commit `.env`, additional model weights, uploads, generated artifacts, virtual
environments, or generated deliverables. This repository's `.gitignore`
enforces those boundaries. The one bundled detector checkpoint is an explicit
exception so a clone can run inference; see [model details](models/README.md).

```powershell
git status
git add .
git diff --cached --check
git commit -m "Describe your change"
```

The configured `origin` points to the project repository. Push your branch to `origin`:

```powershell
git push origin main
```

## Repository layout

```text
src/             FastAPI service, topology/graph code, database model, tests
training/        Reproducible detector training and local inference tools
scripts/         Environment bootstrap scripts
notebooks/       Experiment notebooks
models/          Bundled detector and optional local model weights
artifacts/       Generated training and prediction outputs (not committed)
docs/            Architecture and operational documentation
```

## What is versioned

Source code, tests, dependency specifications, documentation, and bootstrap
scripts and the bundled detector belong in Git. Datasets, project PDFs,
virtual environments, extra checkpoints, and
generated outputs do not; put them in the documented local locations instead.

## Current architecture note

The original FastAPI service keeps its external symbol-detection and Azure
integration contracts under `app.main`. The default web API (`app.web_main`)
invokes the local YOLO/OCR/line/topology pipeline and produces an editable
scene. Original drawings persist in MinIO; drawing metadata, annotations and
symbol definitions persist in PostgreSQL. Pipeline jobs remain in memory.

## Validation

See [DEPLOYMENT.md](DEPLOYMENT.md#kiểm-thử) for regression tests and
`python scripts/smoke_web.py --pipeline` for the deployed end-to-end check.
See [code style](docs/code-style.md) for formatting and lint commands.
CI checks Python and frontend style, builds the UI, and verifies a new Docker
stack from tracked source and an empty database.
