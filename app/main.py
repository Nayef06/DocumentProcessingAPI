import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.routes.auth import router as auth_router
from app.api.routes.documents import router as documents_router
from app.api.routes.health import router as health_router
from app.api.routes.jobs import router as jobs_router
from app.api.routes.search import router as search_router
from app.core.config import settings
from app.schemas.error import sanitized_validation_errors


logger = logging.getLogger(__name__)

OPENAPI_TAGS = [
    {"name": "Health", "description": "Service availability checks."},
    {
        "name": "Authentication",
        "description": "User registration, login, and current-user details.",
    },
    {
        "name": "Documents",
        "description": "Authenticated document upload and lifecycle operations.",
    },
    {
        "name": "Processing Jobs",
        "description": "Asynchronous document-processing job status.",
    },
    {
        "name": "Search",
        "description": "Search across the authenticated user's processed documents.",
    },
]

app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "Authenticated API for uploading, asynchronously processing, and searching "
        "text and PDF documents."
    ),
    version="1.0.0",
    debug=settings.DEBUG,
    openapi_tags=OPENAPI_TAGS,
)


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    logger.info(
        "Request validation failed for %s %s",
        request.method,
        request.url.path,
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": sanitized_validation_errors(exc.errors())},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "Unhandled error while serving %s %s",
        request.method,
        request.url.path,
        exc_info=exc,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


app.include_router(health_router)
app.include_router(auth_router)
app.include_router(documents_router)
app.include_router(jobs_router)
app.include_router(search_router)
