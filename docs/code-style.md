# Formatting the annotation and symbol-library code

The annotation workspace and symbol-library screens use Prettier with single
quotes and a 100-column print width. Python API and test files use Ruff with
the same print width and Python 3.11 syntax. Tool versions are pinned so a
fresh checkout produces the same formatting.

From `frontend/`, using the Node version in `package.json`:

```sh
npm ci
npm run format
npm run format:check
npm run lint
npm run build
```

The formatting scripts target the application shell, drawing canvas and the
annotation/symbol-library files. Older screens can be migrated separately.

From the application repository root, inside a Python development environment:

```sh
python -m pip install -r src/requirements.dev.txt
ruff check --select I src/app/annotations.py src/app/web_main.py src/app/symbol_library.py tests/test_annotations.py tests/test_symbol_library.py
ruff format --check src/app/annotations.py src/app/web_main.py src/app/symbol_library.py tests/test_annotations.py tests/test_symbol_library.py
PYTHONPATH=src python -m unittest discover -s tests -p 'test_annotations.py' -v
PYTHONPATH=src python -m unittest discover -s tests -p 'test_web_main.py' -v
```

Runtime API/test dependencies are listed in `src/requirements.web.txt`,
`src/requirements.symbol-db.txt` and `src/requirements.test.txt`.
`tests/test_symbol_library.py` uses a disposable PostgreSQL schema when
`SYMBOL_TEST_DATABASE=1`; it does not alter the application's catalog tables.

Source drawings, label crops, datasets, upload folders, generated artifacts,
database files and `.env` values stay local. Before committing, inspect
`git diff --cached --name-only` and stage source paths explicitly.
