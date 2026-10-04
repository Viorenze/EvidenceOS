"""Integration test: upload -> chunk -> jieba -> embed -> database -> vector search -> cascade delete.

Automatically runs when PostgreSQL is available, and cleanly skips if database is offline.
"""

import uuid
import pytest
from sqlalchemy import text
from apps.api.config import get_settings
from apps.api.db.models import Chunk, Document
from apps.api.db.session import engine, init_db, SessionLocal
from apps.api.rag.ingestion import process_document
from apps.api.rag.retrieval import vector_search


def is_postgres_available() -> bool:
    """Check if PostgreSQL container is running and reachable."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1;"))
            return True
    except Exception:
        return False


@pytest.mark.skipif(not is_postgres_available(), reason="PostgreSQL + pgvector is not currently reachable")
def test_live_ingest_search_and_delete_cycle():
    """Live database test: end-to-end ingestion and vector search in pgvector."""
    # Ensure tables and extensions exist
    init_db()

    db = SessionLocal()
    doc_id = str(uuid.uuid4())
    filename = "test_architecture.md"

    doc = Document(
        id=doc_id,
        filename=filename,
        status="processing",
    )
    db.add(doc)
    db.commit()

    sample_md = """# EvidenceOS 混合检索架构

EvidenceOS 采用 pgvector 向量检索与 jieba 全文检索。

## 评测指标

系统使用 Hit@5 与 Citation Precision 进行量化对比。
""".encode("utf-8")
    target_query = "系统使用 Hit@5 与 Citation Precision 进行量化对比。"
    try:
        # 1. Ingestion
        processed_doc = process_document(
            db=db,
            document_id=doc_id,
            file_bytes=sample_md,
            filename=filename,
        )
        assert processed_doc.status == "ready"
        assert processed_doc.n_chunks >= 2

        # 2. Vector search (exact content query matches deterministically with fake embedding)
        results = vector_search(db=db, query=target_query, k=5)
        assert len(results) > 0
        assert results[0]["document_id"] == doc_id
        assert results[0]["score"] > 0.99  # Identical text yields cosine similarity ~1.0

    finally:
        # 3. Always clean up test document and verify cascade delete
        doc_in_db = db.query(Document).filter(Document.id == doc_id).first()
        if doc_in_db:
            db.delete(doc_in_db)
            db.commit()

        remaining_chunks = db.query(Chunk).filter(Chunk.document_id == doc_id).all()
        assert len(remaining_chunks) == 0
        db.close()
