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

        # 2. Vector search
        results = vector_search(db=db, query="评测指标", k=5)
        assert len(results) > 0
        assert any(r["document_id"] == doc_id for r in results)

        # 3. Cascade deletion
        db.delete(processed_doc)
        db.commit()

        # Verify chunks are cascade deleted
        remaining_chunks = db.query(Chunk).filter(Chunk.document_id == doc_id).all()
        assert len(remaining_chunks) == 0

    finally:
        db.close()
