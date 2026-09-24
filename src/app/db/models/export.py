"""SQLAlchemy model for generated exports (JSON, DEXPI-compatible XML, SVG)."""

from __future__ import annotations

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.core.database import Base


class Export(Base):
    __tablename__ = "exports"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    drawing_id = Column(Integer, ForeignKey("drawings.id", ondelete="CASCADE"), nullable=False, index=True)

    export_type = Column(String(50), nullable=False, index=True)  # json, dexpi_xml, svg
    file_path = Column(String(1024), nullable=False)
    content = Column(Text, nullable=True)  # optional cached content string

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    drawing = relationship("Drawing", back_populates="exports")
