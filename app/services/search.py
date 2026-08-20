from sqlalchemy import func, literal_column, select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.text_chunk import TextChunk
from app.schemas.search import SearchResult


TEXT_SEARCH_CONFIG = literal_column("'english'::regconfig")


def search_processed_chunks(
    db: Session,
    *,
    user_id: int,
    query: str,
    limit: int,
) -> list[SearchResult]:
    """Return ranked text-chunk matches from one user's processed documents."""
    search_query = func.websearch_to_tsquery(TEXT_SEARCH_CONFIG, query)
    search_vector = func.to_tsvector(TEXT_SEARCH_CONFIG, TextChunk.content)
    relevance = func.ts_rank(search_vector, search_query).label("score")

    statement = (
        select(
            Document.id.label("document_id"),
            Document.original_filename,
            TextChunk.id.label("chunk_id"),
            TextChunk.chunk_index,
            TextChunk.content.label("snippet"),
            relevance,
        )
        .join(Document, TextChunk.document_id == Document.id)
        .where(
            Document.user_id == user_id,
            Document.status == "PROCESSED",
            search_vector.bool_op("@@")(search_query),
        )
        .order_by(relevance.desc(), Document.id.asc(), TextChunk.chunk_index.asc())
        .limit(limit)
    )

    return [
        SearchResult(
            document_id=row.document_id,
            original_filename=row.original_filename,
            chunk_id=row.chunk_id,
            chunk_index=row.chunk_index,
            snippet=row.snippet,
            score=float(row.score),
        )
        for row in db.execute(statement)
    ]
