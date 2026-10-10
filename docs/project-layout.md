# Project layout and rebuild boundaries

The repository separates versioned source code from local datasets, model
extra weights, virtual environments, and generated results. The bundled
detector at `models/symbol-detector/best.pt` is tracked for fresh-clone inference.

```text
digitization-of-piping-and-instrument-diagrams/
├── src/                    FastAPI application, graph code, SQL graph model, and tests
├── training/
│   └── yolov8s/            Symbol-detector train and preview tools
├── scripts/                Reproducible local setup commands
├── notebooks/              Exploratory and Kaggle notebooks
├── models/                 Bundled detector plus optional ignored local weights
├── artifacts/              Training runs and previews only; ignored by Git
├── docs/                   Architecture, API, and project documentation
├── .devcontainer/          API development container and SQL Server setup
└── .github/                Repository automation templates
```

Outside the repository root, keep non-source material in the workspace:

```text
../data/                    Raw P&ID samples and YOLO datasets
../paper/                   Literature and PDFs
```

## Rebuild order

For the supported web application, follow [DEPLOYMENT.md](../DEPLOYMENT.md):
Docker Compose builds the CPU runtime and starts React, `app.web_main` and
PostgreSQL. The detector is bundled; PaddleOCR downloads its models on first
use. No training dataset or Azure credentials are needed for this path.

The steps below describe the separate legacy API and training workflows.

1. Build the API environment from `src/requirements.txt`, or use the existing
   dev container workflow in `docs/local_development_setup.md`.
2. Build the unified local OCR/YOLO environment with
   `./scripts/bootstrap-ocr.ps1`.
3. Supply a dataset at the layout documented in `training/yolov8s/README.md`.
4. Train or download weights into `models/`.
5. Run previews. The legacy API `app.main` keeps its original external
   endpoint contract; `app.web_main` already invokes the local pipeline.

The last point is deliberate: reorganizing files does not silently change the
runtime architecture or remove Azure dependencies. The migration plan for a
self-hosted pipeline remains in `docs/open-source-rebuild-plan.md`.
