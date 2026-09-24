"""API routes for triggering AI processing jobs and streaming SSE progress."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import AsyncGenerator
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db, SessionLocal
from app.db.repositories.drawing_repository import DrawingRepository
from app.schemas import JobCreateResponse, JobStatusResponse
from app.workers.pipeline_worker import worker_instance

router = APIRouter(prefix="", tags=["processing"])


@router.post("/drawings/{drawing_id}/process", response_model=JobCreateResponse)
def start_processing_job(drawing_id: int, db: Session = Depends(get_db)):
    """Submit a processing job to the AI worker queue."""
    repo = DrawingRepository(db)
    drawing = repo.get_drawing(drawing_id)
    if not drawing:
        raise HTTPException(status_code=404, detail="Drawing not found")

    job_id = f"job_{uuid.uuid4().hex[:12]}"
    repo.create_job(job_id=job_id, drawing_id=drawing_id)
    repo.update_drawing_status(drawing_id=drawing_id, status="PROCESSING")

    # Enqueue into worker
    worker_instance.enqueue_job(job_id=job_id, drawing_id=drawing_id)

    return JobCreateResponse(
        job_id=job_id,
        drawing_id=drawing_id,
        status="QUEUED",
        message="Job successfully submitted to processing queue",
    )


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_job_status(job_id: str, db: Session = Depends(get_db)):
    """Check current status, stage, and progress of a processing job."""
    repo = DrawingRepository(db)
    job = repo.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/jobs/{job_id}/events")
async def stream_job_events(job_id: str):
    """Stream real-time job progress using Server-Sent Events (SSE)."""

    async def event_generator() -> AsyncGenerator[str, None]:
        last_progress = -1
        last_stage = ""

        # Poll database periodically and yield SSE messages
        while True:
            db = SessionLocal()
            try:
                repo = DrawingRepository(db)
                job = repo.get_job(job_id)
                if not job:
                    yield f"event: error\ndata: {json.dumps({'error': 'Job not found'})}\n\n"
                    break

                if job.progress != last_progress or job.current_stage != last_stage:
                    last_progress = job.progress
                    last_stage = job.current_stage
                    data = {
                        "job_id": job.job_id,
                        "status": job.status,
                        "stage": job.current_stage,
                        "progress": job.progress,
                        "metadata": job.stage_metadata,
                        "error_message": job.error_message,
                    }
                    yield f"event: progress\ndata: {json.dumps(data)}\n\n"

                if job.status in ["COMPLETED", "FAILED"]:
                    yield f"event: done\ndata: {json.dumps({'status': job.status})}\n\n"
                    break

            finally:
                db.close()

            await asyncio.sleep(0.8)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
