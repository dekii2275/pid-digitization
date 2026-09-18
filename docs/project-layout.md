# Project layout and rebuild boundaries

The repository separates versioned source code from local datasets, model
weights, virtual environments, and generated results. Those local materials
are intentionally ignored by Git.

```text
digitization-of-piping-and-instrument-diagrams/
├── src/                    FastAPI application, graph code, SQL graph model, and tests
├── training/
│   └── yolov8s/            Symbol-detector train and preview tools
├── scripts/                Reproducible local setup commands
├── notebooks/              Exploratory and Kaggle notebooks
├── models/                 Local weights only; ignored by Git
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

1. Build the API environment from `src/requirements.txt`, or use the existing
   dev container workflow in `docs/local_development_setup.md`.
2. Build the independent YOLO environment with
   `./scripts/bootstrap-yolov8.ps1`.
3. Supply a dataset at the layout documented in `training/yolov8s/README.md`.
4. Train or download weights into `models/`.
5. Run preview or connect the local detector to the API through a dedicated
   adapter; the current API still uses its original external endpoint contract.

The last point is deliberate: reorganizing files does not silently change the
runtime architecture or remove Azure dependencies. The migration plan for a
self-hosted pipeline remains in `docs/open-source-rebuild-plan.md`.
