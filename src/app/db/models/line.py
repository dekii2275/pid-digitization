"""SQLAlchemy model for detected lines and piping geometry."""

from __future__ import annotations

from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship

from app.core.database import Base


class DetectedLine(Base):
    __tablename__ = "lines"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    drawing_id = Column(Integer, ForeignKey("drawings.id", ondelete="CASCADE"), nullable=False, index=True)
    page_id = Column(Integer, ForeignKey("drawing_pages.id", ondelete="SET NULL"), nullable=True, index=True)

    line_type = Column(String(50), nullable=False, default="pipe", index=True)  # pipe, signal, other
    geometry = Column(JSON, nullable=False)  # {"points": [[x1, y1], [x2, y2], ...]}
    confidence = Column(Float, nullable=False, default=1.0)
    flow_direction = Column(String(50), nullable=True)  # left-to-right, right-to-left, bidirectional, unknown

    source = Column(String(50), nullable=False, default="AI")  # AI, USER
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    drawing = relationship("Drawing", back_populates="lines")
    page = relationship("DrawingPage", back_populates="lines")
    relationships = relationship("Relationship", back_populates="line")
