"""Retrieval module supporting Dense Vector Search, PostgreSQL Full-Text Search, and RRF Fusion.

Why this hybrid retrieval design works (Interview Reference):
1. Vector Retrieval (Cosine Distance via pgvector):
   Captures semantic similarities, synonyms, and conceptual intent.
   Weakness: Can miss specific keywords, configuration names, or exact error codes.
2. Full-Text Search (ts_rank_cd over jieba-segmented tokens):
   Enforces lexical match for exact technical identifiers (e.g., 'EMBEDDING_PROVIDER', 'pgvector').
   jieba pre-segments Chinese text into `content_seg`, indexed by `to_tsvector('simple', ...)`.
   `ts_rank_cd` measures cover density (how close matching words appear in the chunk).
3. RRF (Reciprocal Rank Fusion, k=60):
   Combines rank lists from both systems: RRF_score(d) = sum(1 / (60 + rank_i(d))).
   - Scale-independent: avoids calibrating incompatible score distributions (cosine vs ts_rank).
   - Robust: rewarding documents retrieved by both methods while preventing single-method outlier domination.
   - All parameters (top-k, RRF constant) are driven by configuration.
"""

import re
from typing import Any, Dict, List, Optional
import jieba
from sqlalchemy import func, literal_column, select
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.db.models import Chunk, Document
from apps.api.rag.embeddings import get_embedding_provider


def vector_search(
    db: Session,
    query: str,
    k: int = 20,
) -> List[Dict[str, Any]]:
    """Retrieve top-k chunks ordered by cosine similarity to the query embedding."""
    if not query.strip():
        return []

    settings = get_settings()
    k = k or settings.vector_top_k

    provider = get_embedding_provider()
    query_vector = provider.embed_query(query)

    # Cosine distance operator (<=> in pgvector)
    distance_col = Chunk.embedding.cosine_distance(query_vector).label("distance")

    stmt = (
        select(
            Chunk.id,
            Chunk.document_id,
            Chunk.idx,
            Chunk.page,
            Chunk.heading,
            Chunk.content,
            Document.filename,
            distance_col,
        )
        .join(Document, Chunk.document_id == Document.id)
        .where(Chunk.embedding.is_not(None))
        .order_by(distance_col.asc())
        .limit(k)
    )

    results = db.execute(stmt).all()

    items = []
    for r in results:
        # Convert cosine distance to similarity score: similarity = 1 - distance
        score = 1.0 - float(r.distance) if r.distance is not None else 0.0
        items.append({
            "chunk_id": r.id,
            "document_id": r.document_id,
            "document": r.filename,
            "idx": r.idx,
            "page": r.page,
            "heading": r.heading,
            "content": r.content,
            "score": round(score, 4),
        })

    return items


def fulltext_search(
    db: Session,
    query: str,
    k: int = 20,
) -> List[Dict[str, Any]]:
    """Retrieve top-k chunks ordered by ts_rank_cd using jieba segmentation."""
    if not query.strip():
        return []

    settings = get_settings()
    k = k or settings.fulltext_top_k

    # 1. Segment query with jieba, filter and clean alphanumeric & Chinese tokens
    words = [
        re.sub(r"[^\w\u4e00-\u9fff]", "", w)
        for w in jieba.cut(query)
    ]
    tokens = [w for w in words if w.strip()]
    if not tokens:
        return []

    # Join tokens with OR (|) to recall chunks matching any keyword
    # ts_rank_cd naturally ranks chunks matching more words in close proximity higher
    tsquery_expr = " | ".join(tokens)

    # 2. Query PostgreSQL with ts_rank_cd and GIN index
    rank_col = func.ts_rank_cd(
        Chunk.tsv,
        func.to_tsquery(literal_column("'simple'"), tsquery_expr),
    ).label("rank")

    stmt = (
        select(
            Chunk.id,
            Chunk.document_id,
            Chunk.idx,
            Chunk.page,
            Chunk.heading,
            Chunk.content,
            Document.filename,
            rank_col,
        )
        .join(Document, Chunk.document_id == Document.id)
        .where(
            Chunk.tsv.op("@@")(
                func.to_tsquery(literal_column("'simple'"), tsquery_expr)
            )
        )
        .order_by(rank_col.desc())
        .limit(k)
    )

    results = db.execute(stmt).all()

    items = []
    for r in results:
        score = float(r.rank) if r.rank is not None else 0.0
        items.append({
            "chunk_id": r.id,
            "document_id": r.document_id,
            "document": r.filename,
            "idx": r.idx,
            "page": r.page,
            "heading": r.heading,
            "content": r.content,
            "score": round(score, 4),
        })

    return items


def rrf_fusion(
    vector_results: List[Dict[str, Any]],
    fulltext_results: List[Dict[str, Any]],
    rrf_k: int = 60,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """Fuse ranked lists from vector and full-text retrieval using Reciprocal Rank Fusion.

    Formula:
        RRF_score(d) = sum_{m in {vector, fulltext}} (1 / (rrf_k + rank_m(d)))
    where rank_m(d) is the 1-indexed rank of document d in method m.
    """
    scores: Dict[str, float] = {}
    chunk_map: Dict[str, Dict[str, Any]] = {}
    vector_ranks: Dict[str, int] = {}
    fulltext_ranks: Dict[str, int] = {}

    for rank, item in enumerate(vector_results, start=1):
        cid = item["chunk_id"]
        chunk_map[cid] = item
        vector_ranks[cid] = rank
        scores[cid] = scores.get(cid, 0.0) + (1.0 / (rrf_k + rank))

    for rank, item in enumerate(fulltext_results, start=1):
        cid = item["chunk_id"]
        if cid not in chunk_map:
            chunk_map[cid] = item
        fulltext_ranks[cid] = rank
        scores[cid] = scores.get(cid, 0.0) + (1.0 / (rrf_k + rank))

    # Sort chunks by RRF score descending
    sorted_chunk_ids = sorted(scores.keys(), key=lambda cid: scores[cid], reverse=True)

    fused_results = []
    for cid in sorted_chunk_ids[:top_k]:
        item = dict(chunk_map[cid])
        item["score"] = round(scores[cid], 6)
        item["rrf_score"] = round(scores[cid], 6)
        item["vector_rank"] = vector_ranks.get(cid)
        item["fulltext_rank"] = fulltext_ranks.get(cid)
        fused_results.append(item)

    return fused_results


def hybrid_search(
    db: Session,
    query: str,
    vector_k: Optional[int] = None,
    fulltext_k: Optional[int] = None,
    rrf_k: Optional[int] = None,
    top_k: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Execute hybrid retrieval: vector top-20 + full-text top-20 -> RRF fusion top-5."""
    settings = get_settings()
    vk = vector_k or settings.vector_top_k
    fk = fulltext_k or settings.fulltext_top_k
    rk = rrf_k or settings.rrf_k
    tk = top_k or settings.final_top_k

    vec_results = vector_search(db=db, query=query, k=vk)
    ft_results = fulltext_search(db=db, query=query, k=fk)

    return rrf_fusion(
        vector_results=vec_results,
        fulltext_results=ft_results,
        rrf_k=rk,
        top_k=tk,
    )
