"""SQLAlchemy ORM models for EvidenceOS.

Three locked tables as specified in PRD Section 5:
1. `documents`: metadata and processing state of uploaded source files.
2. `chunks`: text chunks with heading breadcrumbs, jieba-segmented text,
            PostgreSQL tsvector (GIN indexed), and pgvector embedding (HNSW indexed).
3. `runs`: execution history of queries, answers, citations array, and agent steps array.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, List

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Column,
    Computed,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Document(Base):
    """Stores uploaded document records and their ingestion lifecycle."""

    __tablename__ = "documents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    filename = Column(String(255), nullable=False)
    status = Column(String(50), nullable=False, default="processing")  # processing / ready / failed
    n_chunks = Column(Integer, nullable=False, default=0)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    chunks = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")


class Chunk(Base):
    """Stores text chunks with vector embeddings and full-text search tokens."""

    __tablename__ = "chunks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(
        String(36),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    idx = Column(Integer, nullable=False)
    page = Column(Integer, nullable=True)
    heading = Column(String(500), nullable=True)
    content = Column(Text, nullable=False)
    content_seg = Column(Text, nullable=False)  # Pre-segmented Chinese words separated by spaces
    tsv = Column(
        TSVECTOR,
        Computed("to_tsvector('simple', content_seg)", persisted=True),
        nullable=True,
    )
    embedding = Column(Vector(512), nullable=True)

    document = relationship("Document", back_populates="chunks")

    __table_args__ = (
        Index("idx_chunks_tsv", "tsv", postgresql_using="gin"),
        Index(
            "idx_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


class Run(Base):
    """Stores query execution runs, citation links, agent steps, and latency metrics."""

    __tablename__ = "runs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    question = Column(Text, nullable=False)
    mode = Column(String(50), nullable=False, default="hybrid")
    answer = Column(Text, nullable=True)
    # JSON array semantics for citations and steps
    citations = Column(JSONB, nullable=False, default=list)
    steps = Column(JSONB, nullable=False, default=list)
    refused = Column(Boolean, nullable=False, default=False)
    latency_ms = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
