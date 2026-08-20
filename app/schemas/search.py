from pydantic import BaseModel


class SearchResult(BaseModel):
    document_id: int
    original_filename: str
    chunk_id: int
    chunk_index: int
    snippet: str
    score: float


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
