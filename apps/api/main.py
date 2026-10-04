"""FastAPI application entry point for EvidenceOS.

Assembles routers for health check, documents ingestion, chunk provenance,
and vector/hybrid search. Automatically ensures database tables and pgvector
extension exist on startup.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.db.session import init_db
from apps.api.routers import chat, documents, health, search


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run database initialization on application startup."""
    try:
        init_db()
    except Exception as e:
        # If DB is not reachable during isolated unit test runs, log gracefully
        print(f"[EvidenceOS] Database initialization skipped or deferred: {e}")
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
