from fastapi import APIRouter
from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str


router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Check service health",
)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")
