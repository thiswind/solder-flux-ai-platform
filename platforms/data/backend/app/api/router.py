from fastapi import APIRouter

from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.health import router as health_router
from app.api.routes.pipeline import router as pipeline_router
from app.api.routes.vision import router as vision_router
from app.api.routes.user import router as user_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(dashboard_router)
api_router.include_router(pipeline_router)
api_router.include_router(vision_router)
api_router.include_router(user_router)
