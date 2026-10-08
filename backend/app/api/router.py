from fastapi import APIRouter
from app.api.v1 import jobs, certificates

api_router = APIRouter()
api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
api_router.include_router(certificates.router, prefix="/certificates", tags=["certificates"])
