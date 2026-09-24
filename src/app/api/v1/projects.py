"""API routes for projects."""

from __future__ import annotations

from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.db.repositories.drawing_repository import DrawingRepository
from app.schemas import ProjectCreate, ProjectResponse

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectResponse)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)):
    repo = DrawingRepository(db)
    return repo.create_project(name=payload.name, description=payload.description)


@router.get("", response_model=List[ProjectResponse])
def list_projects(db: Session = Depends(get_db)):
    repo = DrawingRepository(db)
    return repo.list_projects()
