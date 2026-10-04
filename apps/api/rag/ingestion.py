"""Document ingestion pipeline: extraction -> chunking -> jieba segmentation -> embedding -> database storage.

Why this ingestion order matters (Interview Reference):
1. Format-specific chunking preserves structural semantics (Markdown headings, PDF pages).
2. jieba pre-segmentation generates space-delimited tokens in `content_seg`, allowing PostgreSQL's
   built-in 'simple' tsvector parser to index Chinese keywords without third-party C-extensions.
3. Dense vector embeddings are generated in batch via the EmbeddingProvider abstraction.
4. Database insertion happens inside a single ACID transaction: either all chunks are committed
   and document status becomes 'ready', or status becomes 'failed' with error detail.
"""

from typing import List
import jieba
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.db.models import Chunk, Document
from apps.api.rag.chunker import RawChunk, chunk_markdown, chunk_pdf
from apps.api.rag.embeddings import get_embedding_provider


def process_document(
    db: Session,
    document_id: str,
    file_bytes: bytes,
    filename: str,
) -> Document:
    """Ingest a document end-to-end and update its database record status."""
    settings = get_settings()
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise ValueError(f"Document with id {document_id} not found")

    try:
        lower_name = filename.lower()
        if lower_name.endswith(".pdf"):
            raw_chunks = chunk_pdf(
                file_bytes=file_bytes,
                chunk_size=settings.chunk_size,
                chunk_overlap=settings.chunk_overlap,
            )
        elif lower_name.endswith((".md", ".markdown", ".txt")):
            text = file_bytes.decode("utf-8", errors="replace")
            raw_chunks = chunk_markdown(
                content=text,
                chunk_size=settings.chunk_size,
                chunk_overlap=settings.chunk_overlap,
            )
        else:
            raise ValueError(f"Unsupported file format: {filename}. Only .md and .pdf are supported.")

        if not raw_chunks:
            raise ValueError("No extractable content found in document.")

        # 1. Chinese word segmentation for PostgreSQL full-text search
        contents_seg: List[str] = [
            " ".join(jieba.cut(c.content)) for c in raw_chunks
        ]

        # 2. Dense vector embeddings batch calculation
        provider = get_embedding_provider()
        embeddings = provider.embed_documents([c.content for c in raw_chunks])

        # 3. Create Chunk ORM entities
        for c, seg, emb in zip(raw_chunks, contents_seg, embeddings):
            chunk_row = Chunk(
                document_id=doc.id,
                idx=c.idx,
                page=c.page,
                heading=c.heading,
                content=c.content,
                content_seg=seg,
                embedding=emb,
            )
            db.add(chunk_row)

        doc.status = "ready"
        doc.n_chunks = len(raw_chunks)
        doc.error = None
        db.commit()
        db.refresh(doc)
        return doc

    except Exception as e:
        db.rollback()
        doc.status = "failed"
        doc.error = str(e)
        db.commit()
        db.refresh(doc)
        raise e
