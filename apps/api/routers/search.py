"""Search endpoint for evaluation and debugging matching PRD Section 6."""

from typing import Any, Dict, List, Literal, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.db.session import get_db
from apps.api.rag.retrieval import hybrid_search, vector_search

router = APIRouter(prefix="/api", tags=["search"])


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Query string to search for")
    mode: Literal["vector", "hybrid"] = Field(
        default="hybrid",
        description="Retrieval mode: vector (dense only) or hybrid (vector + fulltext + RRF)",
    )
    k: Optional[int] = Field(default=None, ge=1, le=100, description="Top-k candidates to retrieve")


class SearchItem(BaseModel):
    chunk_id: str
    document_id: str
    document: str
    idx: int
    page: Optional[int] = None
    heading: Optional[str] = None
    content: str
    score: float
    vector_rank: Optional[int] = None
    fulltext_rank: Optional[int] = None


class SearchResponse(BaseModel):
    query: str
    mode: str
    results: List[SearchItem]


@router.post("/search", response_model=SearchResponse)
def search(req: SearchRequest, db: Session = Depends(get_db)):
    """Search knowledge base chunks for evaluation and debugging.

    Supports mode="vector" (cosine similarity) and mode="hybrid" (RRF fusion of vector and ts_rank_cd).
    """
    settings = get_settings()

    if req.mode == "vector":
        k = req.k or settings.vector_top_k
        items = vector_search(db=db, query=req.query, k=k)
    else:  # hybrid
        k = req.k or settings.final_top_k
        items = hybrid_search(
            db=db,
            query=req.query,
            vector_k=settings.vector_top_k,
            fulltext_k=settings.fulltext_top_k,
            rrf_k=settings.rrf_k,
            top_k=k,
        )

    return SearchResponse(
        query=req.query,
        mode=req.mode,
        results=[SearchItem(**item) for item in items],
    )
