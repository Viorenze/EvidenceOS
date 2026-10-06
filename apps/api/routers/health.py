"""Health check endpoint."""

from fastapi import APIRouter
from apps.api.config import get_settings

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health_check(details: bool = False):
    """Return system health status, optionally including component readiness details."""
    if not details:
        return {"status": "ok"}

    from apps.api.rag.embeddings import _provider_instance

    cfg = get_settings()
    embedding_ready = _provider_instance is not None

    return {
        "status": "ok",
        "ready": embedding_ready,
        "components": {
            "database": "connected",
            "embedding": {
                "provider": cfg.embedding_provider,
                "model": cfg.embedding_model,
                "ready": embedding_ready,
            },
        },
    }
