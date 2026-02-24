"""API v1 Router - Aggregates all endpoint routers."""

from fastapi import APIRouter

from app.api.v1.chat import router as chat_router
from app.api.v1.search import router as search_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.alerts import router as alerts_router
from app.api.v1.users import router as users_router
from app.api.v1.auth import router as auth_router

router = APIRouter()

# Include all routers
router.include_router(auth_router, prefix="/auth", tags=["Authentication"])
router.include_router(users_router, prefix="/users", tags=["Users"])
router.include_router(chat_router, prefix="/chat", tags=["Chat"])
router.include_router(search_router, prefix="/search", tags=["Search"])
router.include_router(dashboard_router, prefix="/dashboard", tags=["Dashboard"])
router.include_router(alerts_router, prefix="/alerts", tags=["Alerts"])
