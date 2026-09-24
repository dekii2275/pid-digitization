"""Pipeline orchestration for a single uploaded P&ID drawing."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from app.core import database
from app.core.config import settings
from app.db.repositories.drawing_repository import DrawingRepository
from app.services.pipeline.yolo_detector import YoloSymbolDetector, category_for_class

logger = logging.getLogger(__name__)


class PipelineService:
    def __init__(self, session_factory: Optional[Callable[[], Any]] = None) -> None:
        self.models_dir = settings.MODELS_DIR
        self.session_factory = session_factory or database.SessionLocal
        self.symbol_detector = YoloSymbolDetector(
            weights_path=settings.YOLO_WEIGHTS_PATH,
            device=settings.AI_DEVICE,
        )

    def run_pipeline(
        self,
        job_id: str,
        drawing_id: int,
        progress_callback: Optional[Callable[[str, int, Optional[Dict[str, Any]]], None]] = None,
    ) -> None:
        """Run the trained YOLO symbol detector against this job's upload only."""
        db = self.session_factory()
        repo = DrawingRepository(db)

        def update_progress(
            stage: str,
            progress: int,
            metadata: Optional[Dict[str, Any]] = None,
            status: str = "RUNNING",
        ) -> None:
            repo.update_job_progress(
                job_id=job_id,
                stage=stage,
                progress=progress,
                status=status,
                metadata=metadata,
            )
            if progress_callback:
                progress_callback(stage, progress, metadata)

        try:
            drawing = repo.get_drawing(drawing_id)
            if not drawing:
                raise ValueError(f"Drawing {drawing_id} not found")

            source_path = Path(drawing.file_path)
            update_progress("PREPROCESSING", 10, {"file": source_path.name})
            if not source_path.is_file():
                raise FileNotFoundError(f"Uploaded drawing does not exist: {source_path}")
            if drawing.file_type != "image":
                raise ValueError("YOLO symbol detection currently accepts raster image uploads only.")

            # A re-run replaces generated data from that drawing only. Any human
            # corrections (source=USER) are intentionally kept.
            repo.delete_ai_results(drawing_id)
            repo.update_drawing_status(drawing_id, status="PROCESSING")

            update_progress(
                "DETECTING_SYMBOLS",
                25,
                {
                    "weights": settings.YOLO_WEIGHTS_PATH.name,
                    "confidence_threshold": self.symbol_detector.confidence,
                    "tile_size": self.symbol_detector.tile_size,
                },
            )
            detections = self.symbol_detector.detect_image(source_path)

            update_progress("SAVING_SYMBOLS", 80, {"detections": len(detections)})
            repo.bulk_save_symbols(
                [
                    {
                        "drawing_id": drawing_id,
                        "class_name": detection.class_name,
                        "category": category_for_class(detection.class_name),
                        "bbox_x1": detection.bbox[0],
                        "bbox_y1": detection.bbox[1],
                        "bbox_x2": detection.bbox[2],
                        "bbox_y2": detection.bbox[3],
                        "confidence": detection.confidence,
                        "source": "AI",
                        "model_version": settings.YOLO_WEIGHTS_PATH.name,
                    }
                    for detection in detections
                ]
            )
            repo.update_drawing_status(drawing_id, status="COMPLETED")
            update_progress(
                "COMPLETED",
                100,
                {
                    "detected_symbols": len(detections),
                    "completed_stages": ["YOLO symbol detection"],
                    "pending_stages": ["OCR", "line detection", "topology reconstruction"],
                },
                status="COMPLETED",
            )

        except Exception as exc:
            logger.exception("Pipeline failed for job %s and drawing %s", job_id, drawing_id)
            repo.update_job_progress(
                job_id=job_id,
                stage="FAILED",
                progress=0,
                status="FAILED",
                error_message=str(exc),
            )
            repo.update_drawing_status(drawing_id, status="FAILED")
        finally:
            db.close()
