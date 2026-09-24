"""SQLAlchemy model for OCR texts extracted from drawings."""

from __future__ import annotations

from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.core.database import Base


class OcrText(Base):
    __tablename__ = "ocr_texts"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    drawing_id = Column(Integer, ForeignKey("drawings.id", ondelete="CASCADE"), nullable=False, index=True)
    page_id = Column(Integer, ForeignKey("drawing_pages.id", ondelete="SET NULL"), nullable=True, index=True)

    text = Column(Text, nullable=False, index=True)

    bbox_x1 = Column(Float, nullable=False)
    bbox_y1 = Column(Float, nullable=False)
    bbox_x2 = Column(Float, nullable=False)
    bbox_y2 = Column(Float, nullable=False)

    confidence = Column(Float, nullable=False, default=1.0)
    ocr_engine = Column(String(50), nullable=False, default="PaddleOCR")  # PaddleOCR, PyMuPDF, Manual
    associated_symbol_id = Column(Integer, ForeignKey("symbols.id", ondelete="SET NULL"), nullable=True, index=True)

    source = Column(String(50), nullable=False, default="AI")  # AI, USER
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    drawing = relationship("Drawing", back_populates="ocr_texts")
    page = relationship("DrawingPage", back_populates="ocr_texts")
    associated_symbol = relationship("DetectedSymbol", back_populates="associated_texts")
