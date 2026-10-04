"""Search endpoint for evaluation and debugging matching PRD Section 6."""

from typing import Any, Dict, List, Literal, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.db.session import get_db
from apps.api.rag.retrieval import vector_search

router = APIRouter(prefix="/api", tags=["search"])


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Query string to search for")
    mode: Literal["vector", "hybrid"] = Field(
        default="vector",
        description="Retrieval mode: vector (D1) or hybrid (D2)",
    )
    k: Optional[int] = Field(default=20, ge=1, le=100, description="Top-k candidates to retrieve")


class SearchItem(BaseModel):
    chunk_id: str
    document_id: str
    document: str
    idx: int
    page: Optional[int] = None
    heading: Optional[str] = None
    content: str
    score: float


class SearchResponse(BaseModel):
    query: str
    mode: str
    results: List[SearchItem]


@router.post("/search", response_model=SearchResponse)
def search(req: SearchRequest, db: Session = Depends(get_db)):
    """Search knowledge base chunks for evaluation and debugging.

    D1 implements mode="vector". If mode="hybrid" is requested during D1,
    it executes vector search and reports retrieval results.
    """
    settings = get_settings()
    k = req.k or settings.vector_top_k

    # In D1, dense vector retrieval is active; D2 adds full-text and RRF fusion
    items = vector_search(db=db, query=req.query, k=k)

    return SearchResponse(
        query=req.query,
        mode=req.mode,
        results=[SearchItem(**item) for item in items],
    )
