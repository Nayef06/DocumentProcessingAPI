from fastapi import FastAPI

from app.api.routes.health import router as health_router
from app.core.config import settings


app = FastAPI(title=settings.APP_NAME, debug=settings.DEBUG)
app.include_router(health_router)
