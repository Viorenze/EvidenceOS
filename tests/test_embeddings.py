"""Unit tests for embedding provider abstraction and deterministic fake provider."""

import numpy as np
import pytest
from apps.api.rag.embeddings import FakeEmbeddingProvider, get_embedding_provider


def test_fake_embedding_dimensions_and_normalization():
    """Verify fake embeddings produce 512-dim unit-normalized vectors."""
    provider = FakeEmbeddingProvider(dim=512)
    vec = provider.embed_query("PostgreSQL pgvector 混合检索")

    assert len(vec) == 512
    # Verify L2 norm is 1.0
    norm = np.linalg.norm(vec)
    assert np.isclose(norm, 1.0, atol=1e-5)


def test_fake_embedding_determinism():
    """Verify same text always yields identical vectors, different texts yield different vectors."""
    provider = FakeEmbeddingProvider(dim=512)
    text_a = "LangGraph 有条件循环 Agent"
    text_b = "Next.js 前端流式输出"

    vec_a1 = provider.embed_query(text_a)
    vec_a2 = provider.embed_query(text_a)
    vec_b = provider.embed_query(text_b)

    assert vec_a1 == vec_a2
    assert vec_a1 != vec_b


def test_batch_embed_documents():
    """Verify batch document embedding returns list of 512-dim vectors."""
    provider = FakeEmbeddingProvider(dim=512)
    texts = ["分块算法", "Jieba分词", "RRF融合"]
    embeddings = provider.embed_documents(texts)

    assert len(embeddings) == 3
    for emb in embeddings:
        assert len(emb) == 512
        assert np.isclose(np.linalg.norm(emb), 1.0, atol=1e-5)


def test_get_embedding_provider_singleton():
    """Verify factory returns configured provider instance."""
    provider = get_embedding_provider()
    assert isinstance(provider, FakeEmbeddingProvider)
