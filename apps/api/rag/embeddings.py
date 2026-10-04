"""Embedding provider abstraction layer.

Encapsulates embedding model instantiation behind a unified interface:
- LocalBGEEmbeddingProvider: Uses BAAI/bge-small-zh-v1.5 (512 dims), runs locally.
- FakeEmbeddingProvider: Produces deterministic 512-dim unit vectors for offline testing.

Rule 2: Every embedding call goes through this abstraction. No direct SDK calls in business logic.
"""

from abc import ABC, abstractmethod
import hashlib
from typing import List
import numpy as np

from apps.api.config import get_settings


class EmbeddingProvider(ABC):
    """Abstract base class for all embedding providers."""

    @abstractmethod
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Compute dense vector representations for a list of document chunks."""
        pass

    @abstractmethod
    def embed_query(self, text: str) -> List[float]:
        """Compute dense vector representation for a search query."""
        pass


class FakeEmbeddingProvider(EmbeddingProvider):
    """Deterministic embedding provider for testing.

    Generates a reproducible 512-dimensional normalized float vector
    by seeding a pseudo-random generator with the SHA-256 hash of the input text.
    Ensures unit and integration tests run completely offline and deterministically.
    """

    def __init__(self, dim: int = 512):
        self.dim = dim

    def _generate_vector(self, text: str) -> List[float]:
        # Hash text to create a deterministic integer seed
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        seed = int.from_bytes(digest[:4], "big")
        rng = np.random.default_rng(seed)
        vec = rng.standard_normal(self.dim)
        # L2 normalize
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec.tolist()

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._generate_vector(t) for t in texts]

    def embed_query(self, text: str) -> List[float]:
        return self._generate_vector(text)


class LocalBGEEmbeddingProvider(EmbeddingProvider):
    """Local embedding provider using BAAI/bge-small-zh-v1.5 via SentenceTransformers.

    Produces 512-dimensional normalized embeddings suited for Chinese technical documents.
    """

    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5"):
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_name)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        embeddings = self.model.encode(texts, normalize_embeddings=True)
        return embeddings.tolist()

    def embed_query(self, text: str) -> List[float]:
        # bge-small-zh recommends adding instruction for retrieval query if needed,
        # but standard encode is compatible across standard benchmark evaluations
        embedding = self.model.encode(text, normalize_embeddings=True)
        return embedding.tolist()


_provider_instance: EmbeddingProvider | None = None


def get_embedding_provider() -> EmbeddingProvider:
    """Factory returning the configured singleton embedding provider."""
    global _provider_instance
    if _provider_instance is None:
        settings = get_settings()
        if settings.embedding_provider == "fake":
            _provider_instance = FakeEmbeddingProvider(dim=settings.embedding_dim)
        else:
            _provider_instance = LocalBGEEmbeddingProvider(model_name=settings.embedding_model)
    return _provider_instance
