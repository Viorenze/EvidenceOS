"""Unit tests for embedding provider abstraction and deterministic fake provider."""

import numpy as np
import pytest
from apps.api.rag.embeddings import (
    FakeEmbeddingProvider,
    LocalBGEEmbeddingProvider,
    _FastNumpyBertEngine,
    _resolve_local_hf_snapshot,
    get_embedding_provider,
)


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


@pytest.mark.skipif(
    _resolve_local_hf_snapshot("BAAI/bge-small-zh-v1.5") is None,
    reason="Local HF cache for BAAI/bge-small-zh-v1.5 not present",
)
def test_local_bge_fast_numpy_engine_correctness_and_edge_cases():
    """Verify LocalBGEEmbeddingProvider uses _FastNumpyBertEngine, handles padding/truncation/empty inputs, and normalizes vectors."""
    provider = LocalBGEEmbeddingProvider("BAAI/bge-small-zh-v1.5")
    assert isinstance(provider.model, _FastNumpyBertEngine)

    # Empty list edge case
    assert provider.embed_documents([]) == []

    # Empty string & over-length (>512 tokens) truncation edge cases
    empty_vec = provider.embed_query("")
    long_vec = provider.embed_query("分布式架构与混合检索系统 " * 120)
    assert len(empty_vec) == 512
    assert len(long_vec) == 512
    assert np.isclose(np.linalg.norm(empty_vec), 1.0, atol=1e-5)
    assert np.isclose(np.linalg.norm(long_vec), 1.0, atol=1e-5)

    # Batch padding invariance: single query embedding must match batched embedding with a much longer sequence
    short_text = "FastAPI 异步流式响应"
    long_text = "在 PostgreSQL 中结合 pgvector 向量索引与 jieba 分词全文检索，通过 RRF 算法融合排序结果。"
    single_short = np.array(provider.embed_query(short_text), dtype=np.float32)
    batched = np.array(provider.embed_documents([short_text, long_text]), dtype=np.float32)

    assert batched.shape == (2, 512)
    assert np.allclose(single_short, batched[0], atol=1e-6)
    # Semantic similarity sanity check: related query has higher cosine similarity than unrelated query
    unrelated = np.array(provider.embed_query("今天天气非常适合去公园散步"), dtype=np.float32)
    related = np.array(provider.embed_query("pgvector 向量与全文混合检索 RRF"), dtype=np.float32)
    assert float(np.dot(batched[1], related)) > float(np.dot(batched[1], unrelated))

    # Accented characters + mixed case normalizer parity with SentenceTransformer (must lowercase without stripping accents)
    accented = "Café résumé naïve — PyTorch 2.0 (β) & PostgreSQL pgvector <=>"
    encoded_ids = provider.model.tokenizer.encode(accented).ids
    assert encoded_ids[:6] == [101, 100, 100, 100, 100, 158]


