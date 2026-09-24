"""Asynchronous AI pipeline worker consuming jobs from Redis queue (with in-memory fallback)."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from queue import Queue
from typing import Optional

from app.core.config import settings
from app.services.pipeline.pipeline_service import PipelineService

logger = logging.getLogger(__name__)

# In-memory queue fallback when Redis is not running
_local_job_queue: Queue = Queue()


class PipelineWorker:
    def __init__(self, redis_url: Optional[str] = None) -> None:
        self.redis_url = redis_url or settings.REDIS_URL
        self.service = PipelineService()
        self.redis_client = None

        # Attempt to connect to Redis
        try:
            import redis
            self.redis_client = redis.Redis.from_url(self.redis_url)
            self.redis_client.ping()
            logger.info(f"PipelineWorker connected to Redis: {self.redis_url}")
        except Exception as e:
            logger.warning(f"Redis not available ({e}). Using in-memory fallback queue.")
            self.redis_client = None

    def enqueue_job(self, job_id: str, drawing_id: int) -> None:
        """Enqueue a new processing job for the worker."""
        payload = json.dumps({"job_id": job_id, "drawing_id": drawing_id})
        if self.redis_client:
            try:
                self.redis_client.rpush("pid_job_queue", payload)
                logger.info(f"Enqueued job {job_id} into Redis queue.")
                return
            except Exception as e:
                logger.error(f"Failed to push to Redis: {e}, falling back to local queue.")

        _local_job_queue.put({"job_id": job_id, "drawing_id": drawing_id})
        logger.info(f"Enqueued job {job_id} into local in-memory queue.")

    def process_job(self, job_id: str, drawing_id: int) -> None:
        """Process a single job through the AI pipeline."""
        logger.info(f"Worker processing job {job_id} for drawing {drawing_id}...")
        self.service.run_pipeline(job_id=job_id, drawing_id=drawing_id)
        logger.info(f"Worker finished job {job_id}.")

    def run_worker_loop(self, stop_event: Optional[threading.Event] = None) -> None:
        """Continuously listen for and process jobs."""
        logger.info("PipelineWorker started listening for jobs...")
        while not (stop_event and stop_event.is_set()):
            job = None

            # 1. Try Redis if connected
            if self.redis_client:
                try:
                    result = self.redis_client.blpop("pid_job_queue", timeout=2)
                    if result:
                        _, data = result
                        job = json.loads(data)
                except Exception as e:
                    logger.error(f"Redis pop error: {e}")
                    time.sleep(1)

            # 2. Try in-memory queue if no job from Redis
            if not job and not _local_job_queue.empty():
                try:
                    job = _local_job_queue.get_nowait()
                except Exception:
                    pass

            if job:
                job_id = job.get("job_id")
                drawing_id = job.get("drawing_id")
                if job_id and drawing_id:
                    self.process_job(job_id, drawing_id)
            else:
                time.sleep(0.5)


# Global worker instance
worker_instance = PipelineWorker()


def start_background_worker() -> threading.Thread:
    """Start the worker loop in a background daemon thread for local dev."""
    thread = threading.Thread(target=worker_instance.run_worker_loop, daemon=True)
    thread.start()
    return thread


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Starting standalone AI Pipeline Worker...")
    worker_instance.run_worker_loop()
