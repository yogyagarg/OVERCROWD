# API v1 Router
# Main router that includes all versioned endpoints

from fastapi import APIRouter

api_router = APIRouter(prefix="/api/v1", tags=["v1"])

# Include sub-routers
from . import auth, counters, orders, ai, reports, menu, public

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(counters.router, prefix="/counters", tags=["counters"])
api_router.include_router(orders.router, prefix="/orders", tags=["orders"])
api_router.include_router(ai.router, prefix="/ai", tags=["ai"])
api_router.include_router(reports.router, prefix="/reports", tags=["reports"])
api_router.include_router(menu.router, prefix="/menu", tags=["menu"])
api_router.include_router(public.router, prefix="/public", tags=["public"])