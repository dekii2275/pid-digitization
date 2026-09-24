"""SQLAlchemy models for drawings and multi-page drawings."""

from __future__ import annotations

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.core.database import Base


class Drawing(Base):
    __tablename__ = "drawings"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    original_filename = Column(String(255), nullable=False)
    file_path = Column(String(1024), nullable=False)
    file_type = Column(String(50), nullable=False, default="image")  # "image" or "pdf"
    status = Column(String(50), nullable=False, default="UPLOADED", index=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    page_count = Column(Integer, nullable=False, default=1)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    project = relationship("Project", back_populates="drawings")
    pages = relationship("DrawingPage", back_populates="drawing", cascade="all, delete-orphan")
    symbols = relationship("DetectedSymbol", back_populates="drawing", cascade="all, delete-orphan")
    ocr_texts = relationship("OcrText", back_populates="drawing", cascade="all, delete-orphan")
    lines = relationship("DetectedLine", back_populates="drawing", cascade="all, delete-orphan")
    relationships = relationship("Relationship", back_populates="drawing", cascade="all, delete-orphan")
    jobs = relationship("ProcessingJob", back_populates="drawing", cascade="all, delete-orphan")
    revisions = relationship("Revision", back_populates="drawing", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="drawing", cascade="all, delete-orphan")
    exports = relationship("Export", back_populates="drawing", cascade="all, delete-orphan")


class DrawingPage(Base):
    __tablename__ = "drawing_pages"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    drawing_id = Column(Integer, ForeignKey("drawings.id", ondelete="CASCADE"), nullable=False, index=True)
    page_number = Column(Integer, nullable=False, default=1)
    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)
    image_path = Column(String(1024), nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    drawing = relationship("Drawing", back_populates="pages")
    symbols = relationship("DetectedSymbol", back_populates="page")
    ocr_texts = relationship("OcrText", back_populates="page")
    lines = relationship("DetectedLine", back_populates="page")
