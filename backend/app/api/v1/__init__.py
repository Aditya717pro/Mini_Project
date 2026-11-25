from fastapi import APIRouter

from app.api.routes import access, auth, datasets, etl, reports
from app.api.v1 import health
from app.research_reports.router import router as research_reports_router
from app.synthmed.routes import router as synthmed_router

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(datasets.router)
api_router.include_router(etl.router)
api_router.include_router(reports.router)
api_router.include_router(research_reports_router)
api_router.include_router(access.router)
api_router.include_router(synthmed_router)
