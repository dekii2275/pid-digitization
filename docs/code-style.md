# Code style and validation

All Python source, migrations, training tools, smoke scripts and tests use Ruff,
with Python 3.11 syntax and a 100-column line width. Ruff sorts imports and checks
unused names and common errors. Frontend source, Vite configuration, HTML and
package metadata use Prettier with single quotes, two-space indentation and the
same line width. Oxlint checks frontend source and treats warnings as failures.
Formatter versions are pinned in `src/requirements.dev.txt` and
`frontend/package-lock.json`. `.editorconfig` supplies shared editor defaults.

## Python

From the application repository root, inside a Python development environment:

```sh
python -m pip install -r src/requirements.dev.txt
ruff check --fix src tests scripts training/yolov8s alembic
ruff format src tests scripts training/yolov8s alembic
```

Run the same read-only checks as CI before committing:

```sh
ruff check src tests scripts training/yolov8s alembic
ruff format --check src tests scripts training/yolov8s alembic
python -m compileall -q src training/yolov8s tests scripts alembic
```

The three entrypoints listed in `ruff.toml` deliberately add `src/` to
`sys.path` before importing application modules. Only the import-position rule
is exempted for those files; the remaining checks apply throughout the source.

## Frontend

From `frontend/`, using Node 22 as specified in `package.json`:

```sh
npm ci
npm run format
npm run format:check
npm run lint
npm test
npm run build
```

The format commands cover all of `src/` and `tests/`, including components,
services and Node regression tests, plus `vite.config.js`, `index.html` and
`package.json`. `npm test` uses Node's built-in test runner; it needs no test
framework dependencies.

## API and storage regressions

With the Docker stack running, test dependencies are installed only in the
backend container used for development/testing:

```sh
docker compose exec -T backend pip install -r src/requirements.test.txt
docker compose exec -T backend python -m unittest discover -s tests -p 'test_annotations.py' -v
docker compose exec -T backend python -m unittest discover -s tests -p 'test_web_main.py' -v
docker compose exec -T backend python -m unittest discover -s tests -p 'test_data_management.py' -v
docker compose exec -T -e SYMBOL_TEST_DATABASE=1 backend python -m unittest discover -s tests -p 'test_symbol_library.py' -v
docker compose exec -T -e DOCUMENT_TEST_STORAGE=1 backend python -m unittest discover -s tests -p 'test_document_storage.py' -v
docker compose exec -T -e DOCUMENT_TEST_STORAGE=1 backend python -m unittest discover -s tests -p 'test_assets.py' -v
docker compose exec -T -e DOCUMENT_TEST_STORAGE=1 backend python -m unittest discover -s tests -p 'test_drawing_editor.py' -v
python scripts/smoke_data.py
python scripts/smoke_web.py --pipeline --timeout 1200
```

Runtime API/test dependencies are listed in `src/requirements.web.txt`,
`src/requirements.symbol-db.txt` and `src/requirements.test.txt`.
The MinIO SDK is pinned in `src/requirements.storage.txt`.
`tests/test_symbol_library.py` uses a disposable PostgreSQL schema when
`SYMBOL_TEST_DATABASE=1`; it does not alter the application's catalog tables.
`tests/test_document_storage.py` uses a disposable PostgreSQL schema and MinIO
bucket when `DOCUMENT_TEST_STORAGE=1`. The smoke scripts create their own sample
drawings; `smoke_data.py` removes its drawing after checking the storage flow.
CI runs these checks in a new Docker stack with an empty database.

## Files to commit

Source drawings, label crops, datasets, upload folders, generated artifacts,
database files and `.env` values stay local. Before committing, inspect
`git diff --cached --name-only` and stage source paths explicitly. The bundled
detector checkpoint is the documented exception in [model details](../models/README.md).
