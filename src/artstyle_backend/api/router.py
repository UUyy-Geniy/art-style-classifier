from fastapi import APIRouter

from artstyle_backend.api.routes import admin, tasks, uploads

api_router = APIRouter()
api_router.include_router(uploads.router, prefix="/v1", tags=["upload"])
api_router.include_router(tasks.router, prefix="/v1", tags=["tasks"])
api_router.include_router(admin.router, prefix="/v1/admin", tags=["admin"])

