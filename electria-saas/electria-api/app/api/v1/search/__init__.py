"""Search endpoints - Document and normative search."""

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

router = APIRouter()


class SearchResult(BaseModel):
    """A single search result."""

    id: str
    title: str
    doc_type: str
    source: str
    snippet: str
    relevance_score: float
    published_date: str | None
    url: str | None


class SearchResponse(BaseModel):
    """Response body for search endpoint."""

    results: list[SearchResult]
    total: int
    query: str
    filters_applied: dict


@router.get("")
async def search_documents(
    q: str = Query(..., min_length=2, max_length=500, description="Search query"),
    doc_type: str | None = Query(None, description="Filter by document type"),
    source: str | None = Query(None, description="Filter by source (cne, coordinador, sec)"),
    date_from: str | None = Query(None, description="Filter from date (YYYY-MM-DD)"),
    date_to: str | None = Query(None, description="Filter to date (YYYY-MM-DD)"),
    country_code: str = Query("cl", pattern="^[a-z]{2}$"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> SearchResponse:
    """
    Search through indexed documents.

    Supports filtering by document type, source, and date range.
    Uses hybrid search (vector + keyword) for best results.
    """
    # TODO: Implement search with Pinecone + BM25
    return SearchResponse(
        results=[],
        total=0,
        query=q,
        filters_applied={
            "doc_type": doc_type,
            "source": source,
            "date_from": date_from,
            "date_to": date_to,
            "country_code": country_code,
        },
    )


@router.get("/documents/{document_id}")
async def get_document(document_id: str) -> dict:
    """Get full document details."""
    # TODO: Implement
    return {
        "id": document_id,
        "title": "Documento de ejemplo",
        "content": "Contenido completo del documento...",
    }


@router.get("/suggest")
async def search_suggestions(
    q: str = Query(..., min_length=2, max_length=100),
    limit: int = Query(5, ge=1, le=10),
) -> list[str]:
    """Get search suggestions based on partial query."""
    # TODO: Implement autocomplete
    return []
