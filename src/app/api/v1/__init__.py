"""API v1 router bundle."""

from fastapi import APIRouter

from app.api.v1.projects import router as projects_router
from app.api.v1.drawings import router as drawings_router
from app.api.v1.processing import router as processing_router
from app.api.v1.symbols import router as symbols_router
from app.api.v1.ocr import router as ocr_router
from app.api.v1.lines import router as lines_router
from app.api.v1.topology import router as topology_router
from app.api.v1.search import router as search_router
from app.api.v1.exports import router as exports_router

api_v1_router = APIRouter(prefix="/api/v1")

api_v1_router.include_router(projects_router)
api_v1_router.include_router(drawings_router)
api_v1_router.include_router(processing_router)
api_v1_router.include_router(symbols_router)
api_v1_router.include_router(ocr_router)
api_v1_router.include_router(lines_router)
api_v1_router.include_router(topology_router)
api_v1_router.include_router(search_router)
api_v1_router.include_router(exports_router)
