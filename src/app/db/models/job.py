"""SQLAlchemy model for asynchronous processing jobs."""

from __future__ import annotations

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship

from app.core.database import Base


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    job_id = Column(String(64), unique=True, index=True, nullable=False)
    drawing_id = Column(Integer, ForeignKey("drawings.id", ondelete="CASCADE"), nullable=False, index=True)

    status = Column(String(50), nullable=False, default="QUEUED", index=True)
    # QUEUED, RUNNING, COMPLETED, FAILED
    current_stage = Column(String(50), nullable=False, default="QUEUED")
    # PREPROCESSING, DETECTING_SYMBOLS, RUNNING_OCR, DETECTING_LINES,
    # ASSOCIATING_TAGS, BUILDING_TOPOLOGY, SAVING_RESULTS, COMPLETED
    progress = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    stage_metadata = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    drawing = relationship("Drawing", back_populates="jobs")
