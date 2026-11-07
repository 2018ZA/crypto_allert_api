"""HTTP-роутеры API."""

from api.routes.chart import router as chart_router
from api.routes.health import router as health_router

__all__ = ["chart_router", "health_router"]