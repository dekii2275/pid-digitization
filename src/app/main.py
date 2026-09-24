"""FastAPI main application entrypoint for the P&ID digitization platform."""

from __future__ import annotations

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.api.v1 import api_v1_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="VPI P&ID Digitization Platform",
    description="Digitize P&ID/PFD engineering drawings into structured digital graphs, JSON, and DEXPI-compatible XML.",
    version=settings.VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware for React frontend (localhost:18180, localhost:3000, etc.)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static directories for uploaded drawings and output artifacts
app.mount("/uploads", StaticFiles(directory=str(settings.UPLOADS_DIR)), name="uploads")
app.mount("/artifacts", StaticFiles(directory=str(settings.ARTIFACTS_DIR)), name="artifacts")

# Include API v1 router
app.include_router(api_v1_router)


@app.get("/health", tags=["health"])
def health_check():
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True,
    )
