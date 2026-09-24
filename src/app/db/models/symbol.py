"""SQLAlchemy model for detected symbols on P&ID drawings."""

from __future__ import annotations

from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.core.database import Base


class DetectedSymbol(Base):
    __tablename__ = "symbols"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    drawing_id = Column(Integer, ForeignKey("drawings.id", ondelete="CASCADE"), nullable=False, index=True)
    page_id = Column(Integer, ForeignKey("drawing_pages.id", ondelete="SET NULL"), nullable=True, index=True)

    class_name = Column(String(255), nullable=False, index=True)
    category = Column(String(50), nullable=False, default="Other", index=True)
    # Equipment, Pump, Valve, Instrument, Line, Other

    bbox_x1 = Column(Float, nullable=False)
    bbox_y1 = Column(Float, nullable=False)
    bbox_x2 = Column(Float, nullable=False)
    bbox_y2 = Column(Float, nullable=False)

    confidence = Column(Float, nullable=False, default=1.0)
    tag = Column(String(100), nullable=True, index=True)  # e.g. "P-101", "V-102"
    source = Column(String(50), nullable=False, default="AI")  # AI, USER, IMPORT
    model_version = Column(String(100), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    drawing = relationship("Drawing", back_populates="symbols")
    page = relationship("DrawingPage", back_populates="symbols")
    associated_texts = relationship("OcrText", back_populates="associated_symbol")
