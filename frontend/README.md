# VPI P&ID Studio frontend

React and Vite interface for uploading drawings, reviewing detections, and
editing the extracted P&ID scene. The frontend calls the FastAPI service at
`/api/v1` by default.

## Local development

Use Node.js 22 and install dependencies from this directory:

```powershell
npm ci
npm run dev
```

Vite serves the UI at `http://localhost:18180` and proxies `/api` to the
backend at `http://localhost:18732`. Start that backend with Docker Compose
from the parent directory:

```powershell
cd ..
docker compose up --build -d
```

The Docker UI is at `http://localhost:18731`; Nginx forwards `/api/` to the
backend container.

## Checks

```powershell
npm run lint
npm run build
```
