"""Application settings and configuration for the P&ID digitization platform."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


SRC_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = SRC_ROOT / "app"
REPO_ROOT = SRC_ROOT.parent
WORKSPACE_ROOT = REPO_ROOT.parent

# Load repository-local development settings when present. Docker Compose passes
# the same values through the process environment, which takes precedence.
load_dotenv(REPO_ROOT / ".env", override=False)


class Settings:
    # Project info
    PROJECT_NAME: str = "vpi_detect_and_ocr"
    VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api/v1"

    # Host & Port
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))

    # Database
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "postgres")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "pid_db")
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT: str = os.getenv("POSTGRES_PORT", "15439")

    # SQLAlchemy Database URL
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}",
    )

    # Redis Queue
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: str = os.getenv("REDIS_PORT", "16389")
    REDIS_URL: str = os.getenv("REDIS_URL", f"redis://{REDIS_HOST}:{REDIS_PORT}/0")

    # File storage paths
    UPLOADS_DIR: Path = Path(os.getenv("UPLOADS_DIR", str(REPO_ROOT / "uploads")))
    ARTIFACTS_DIR: Path = Path(os.getenv("ARTIFACTS_DIR", str(REPO_ROOT / "artifacts")))
    MODELS_DIR: Path = Path(os.getenv("MODELS_DIR", str(REPO_ROOT / "models")))

    # AI Configuration
    AI_DEVICE: str = os.getenv("AI_DEVICE", "auto")  # auto, cuda, cpu
    YOLO_WEIGHTS_PATH: Path = MODELS_DIR / "symbol-detector" / "best.pt"

    def __init__(self) -> None:
        self.UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        self.ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        self.MODELS_DIR.mkdir(parents=True, exist_ok=True)


settings = Settings()
