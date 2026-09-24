"""SQLAlchemy model for topological graph relationships between symbols."""

from __future__ import annotations

from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.core.database import Base


class Relationship(Base):
    __tablename__ = "relationships"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    drawing_id = Column(Integer, ForeignKey("drawings.id", ondelete="CASCADE"), nullable=False, index=True)

    from_symbol_id = Column(Integer, ForeignKey("symbols.id", ondelete="CASCADE"), nullable=False, index=True)
    to_symbol_id = Column(Integer, ForeignKey("symbols.id", ondelete="CASCADE"), nullable=False, index=True)

    relation_type = Column(String(50), nullable=False, default="connected_to", index=True)
    # connected_to, measures, flows_to, contains

    line_id = Column(Integer, ForeignKey("lines.id", ondelete="SET NULL"), nullable=True, index=True)
    line_tag = Column(String(100), nullable=True)  # e.g. "6\"-P-1001"

    confidence = Column(Float, nullable=False, default=1.0)
    source = Column(String(50), nullable=False, default="AI")  # AI, USER

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    drawing = relationship("Drawing", back_populates="relationships")
    from_symbol = relationship("DetectedSymbol", foreign_keys=[from_symbol_id])
    to_symbol = relationship("DetectedSymbol", foreign_keys=[to_symbol_id])
    line = relationship("DetectedLine", back_populates="relationships")
