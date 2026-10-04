"""Vector retrieval module using pgvector cosine distance.

Why this retrieval works (Interview Reference):
1. pgvector cosine distance:
   Uses the `<=>` operator (cosine distance = 1 - cosine_similarity).
   For normalized embeddings (like bge-small-zh-v1.5 and FakeEmbeddingProvider),
   cosine distance strictly correlates with semantic similarity.
2. HNSW index acceleration:
   The HNSW index allows approximate nearest neighbor search in sub-millisecond time
   without scanning all chunks sequentially.
3. D1 Scope Notice:
   D1 implements single-path dense vector retrieval. Hybrid retrieval (vector + tsvector + RRF)
   is scheduled for D2.
"""

from typing import Any, Dict, List
from sqlalchemy import select
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
