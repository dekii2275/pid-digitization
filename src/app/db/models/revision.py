"""SQLAlchemy models for revisions and audit logs (Human-in-the-loop tracking)."""

from __future__ import annotations

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship

from app.core.database import Base


class Revision(Base):
    __tablename__ = "revisions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    drawing_id = Column(Integer, ForeignKey("drawings.id", ondelete="CASCADE"), nullable=False, index=True)

    entity_type = Column(String(50), nullable=False, index=True)  # symbol, ocr, line, relationship
    entity_id = Column(Integer, nullable=False, index=True)
    action = Column(String(50), nullable=False)  # CREATE, UPDATE, DELETE

    before_state = Column(JSON, nullable=True)
    after_state = Column(JSON, nullable=True)

    user_identifier = Column(String(100), nullable=False, default="engineer")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    drawing = relationship("Drawing", back_populates="revisions")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    drawing_id = Column(Integer, ForeignKey("drawings.id", ondelete="CASCADE"), nullable=False, index=True)

    action = Column(String(100), nullable=False, index=True)
    details = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    drawing = relationship("Drawing", back_populates="audit_logs")
