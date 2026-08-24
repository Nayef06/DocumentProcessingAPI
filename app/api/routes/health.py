from fastapi import APIRouter
from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"]


router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Check service health",
)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")
