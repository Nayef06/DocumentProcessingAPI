from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.search import SearchResponse
from app.schemas.error import ClientErrorResponse, ErrorResponse
from app.services.search import search_processed_chunks


router = APIRouter(tags=["Search"])


@router.get(
    "/search",
    response_model=SearchResponse,
    summary="Search processed documents",
    description=(
        "Return ranked text-chunk matches from processed documents owned by the "
        "authenticated user."
    ),
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "model": ClientErrorResponse,
            "description": "The query is blank or request validation failed.",
        },
    },
)
def search_documents(
    q: Annotated[
        str,
        Query(
            min_length=1,
            max_length=500,
            description="Words or phrases to find in processed document chunks",
        ),
    ],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[
        int,
        Query(ge=1, le=100, description="Maximum number of results to return"),
    ] = 20,
) -> SearchResponse:
    query = q.strip()
    if not query:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Search query must not be blank",
        )

    return SearchResponse(
        query=query,
        results=search_processed_chunks(
            db,
            user_id=current_user.id,
            query=query,
            limit=limit,
        ),
    )
