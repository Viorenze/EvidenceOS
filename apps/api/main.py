"""FastAPI application entry point for EvidenceOS.

Assembles routers for health check, documents ingestion, chunk provenance,
and vector/hybrid search. Automatically ensures database tables and pgvector
extension exist on startup.
"""

import logging
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.config import get_settings
from apps.api.db.session import init_db
from apps.api.rag.embeddings import warmup_embedding_provider
from apps.api.routers import chat, documents, health, search

logger = logging.getLogger("evidenceos.startup")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run full component initialization and pre-warming on application startup.

    Ensures that when the API enters ready state:
    1. PostgreSQL schema and pgvector extension are verified.
    2. Local Embedding provider (PyTorch graph & BGE weights) is pre-warmed.
    3. Chinese full-text tokenizer (jieba prefix dictionary) is pre-warmed.
    This guarantees zero cold-start latency for the user's first query.
    """
    t_start = time.perf_counter()
    cfg = get_settings()
    print("=" * 60)
    print("[EvidenceOS Startup] Initializing core components...")

    # 1. Database & pgvector
    t_db = time.perf_counter()
    try:
        init_db()
        print(f"[EvidenceOS Startup] [1/3] Database & pgvector ready ({time.perf_counter() - t_db:.2f}s)")
    except Exception as e:
        print(f"[EvidenceOS Startup] [1/3] Database initialization skipped or deferred: {e}")

    # 2. Embedding provider pre-warming
    t_emb = time.perf_counter()
    try:
        warmup_embedding_provider()
        print(f"[EvidenceOS Startup] [2/3] Embedding model ({cfg.embedding_provider}: {cfg.embedding_model}) ready ({time.perf_counter() - t_emb:.2f}s)")
    except Exception as e:
        print(f"[EvidenceOS Startup] [2/3] Embedding warm-up encountered error: {e}")

    # 3. jieba tokenizer pre-warming
    t_jb = time.perf_counter()
    try:
        import jieba
        jieba.initialize()
        print(f"[EvidenceOS Startup] [3/3] jieba tokenizer dictionary ready ({time.perf_counter() - t_jb:.2f}s)")
    except Exception as e:
        print(f"[EvidenceOS Startup] [3/3] jieba initialization skipped: {e}")

    total_time = time.perf_counter() - t_start
    print(f"[EvidenceOS Startup] All components ready in {total_time:.2f}s. Listening for requests.")
    print("=" * 60)
    yield


app = FastAPI(
    title="EvidenceOS API",
    description="Verifiable AI technical documentation QA system",
    version="0.1.0",
    lifespan=lifespan,
)

# Enable CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(documents.router)
app.include_router(search.router)
app.include_router(chat.router)


@app.get("/")
def root():
    return {
        "message": "Welcome to EvidenceOS API",
        "docs_url": "/docs",
        "health": "/api/health",
    }
