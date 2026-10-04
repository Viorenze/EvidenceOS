"""Unit tests for citation extraction, validation, and answer cleanup."""

from apps.api.agent.citations import (
    clean_answer_citations,
    extract_citation_numbers,
    verify_citations,
)


def test_extract_citation_numbers():
    assert extract_citation_numbers("") == []
    assert extract_citation_numbers("没有任何引用") == []
    assert extract_citation_numbers("根据文档 [1] 以及 [2]，结果如下 [1]。") == [1, 2]
    assert extract_citation_numbers("多位数字 [10] 和 [5]") == [10, 5]


def test_clean_answer_citations_removes_illegal_markers():
    text = "FastAPI 提供依赖注入 [1]，同时支持量子计算 [99] 和未验证引用 [0]。"
    valid_numbers = {1}
    cleaned = clean_answer_citations(text, valid_numbers)
    # [1] is preserved, [99] and [0] are removed cleanly
    assert "[1]" in cleaned
    assert "[99]" not in cleaned
    assert "[0]" not in cleaned
    assert "FastAPI 提供依赖注入 [1]，同时支持量子计算 和未验证引用。" in cleaned


def test_clean_answer_citations_empty_valid():
    text = "这包含非法引用 [3] 和 [4]。"
    cleaned = clean_answer_citations(text, valid_numbers=set())
    assert "[3]" not in cleaned
    assert "[4]" not in cleaned
    assert cleaned == "这包含非法引用 和。"


def test_verify_citations_success():
    chunks = [
        {
            "id": "chunk-1",
            "document_filename": "fastapi_overview.md",
            "page": 1,
            "heading": "Dependency Injection",
            "content": "FastAPI has a very powerful and intuitive Dependency Injection system.",
        },
        {
            "id": "chunk-2",
            "document_filename": "pgvector.md",
            "page": 2,
            "heading": "HNSW Index",
            "content": "pgvector supports HNSW indexes for fast approximate nearest neighbor search.",
        },
    ]

    answer = "FastAPI 具备强大的依赖注入系统 [1]，支持向量检索 [2]，并且测试非法标记 [99]。"
    cleaned_ans, citations, is_valid = verify_citations(answer, chunks)

    assert is_valid is True
    assert len(citations) == 2

    # Check first citation
    assert citations[0]["n"] == 1
    assert citations[0]["chunk_id"] == "chunk-1"
    assert citations[0]["document"] == "fastapi_overview.md"
    assert citations[0]["page"] == 1
    assert citations[0]["heading"] == "Dependency Injection"
    assert "Dependency Injection system" in citations[0]["snippet"]

    # Check second citation
    assert citations[1]["n"] == 2
    assert citations[1]["chunk_id"] == "chunk-2"
    assert citations[1]["document"] == "pgvector.md"

    # Verify illegal citation [99] was removed from final cleaned answer
    assert "[1]" in cleaned_ans
    assert "[2]" in cleaned_ans
    assert "[99]" not in cleaned_ans


def test_verify_citations_all_invalid():
    chunks = [
        {"id": "chunk-1", "document_filename": "test.md", "content": "Sample content"},
    ]
    answer = "引用的序号均不存在 [5] 以及 [10]。"
    cleaned_ans, citations, is_valid = verify_citations(answer, chunks)

    assert is_valid is False
    assert citations == []
    assert "[5]" not in cleaned_ans
    assert "[10]" not in cleaned_ans


def test_verify_citations_no_citations_in_text():
    chunks = [{"id": "chunk-1", "content": "Sample"}]
    answer = "回答没有任何方括号引用标记。"
    cleaned_ans, citations, is_valid = verify_citations(answer, chunks)

    assert is_valid is False
    assert citations == []
    assert cleaned_ans == answer
