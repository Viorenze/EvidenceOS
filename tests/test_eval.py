"""Unit tests for evals/runner.py metric calculations and boundary cases.

Verifies:
- Hit@k boundary conditions (rank cutoffs, empty chunks, whitespace)
- Gold-snippet Citation Precision (empty citations, 0-division, partial hit)
- Macro-average Citation Precision
- Refusal Accuracy, Unanswerable Refusal Rate, and Answerable Rejection Rate
- Deterministic Percentile linear interpolation (empty list, single element, p0, p50, p95, p100)
- Consolidated aggregation logic
"""

import math
import pytest
from unittest.mock import MagicMock

from evals.runner import (
    aggregate_mode_metrics,
    calculate_gold_snippet_citation_precision,
    calculate_hit_at_k,
    calculate_macro_citation_precision,
    calculate_percentile,
    calculate_refusal_accuracy,
    check_corpus_ready,
)


# ==============================================================================
# 1. Hit@k Tests
# ==============================================================================


def test_hit_at_k_hit_in_top_k():
    chunks = [
        {"content": "无关内容 A"},
        {"content": "这里是关键证据：基于 Starlette 和 Pydantic 构建。"},
        {"content": "无关内容 B"},
    ]
    assert calculate_hit_at_k(chunks, "Starlette 和 Pydantic", k=5) is True
    assert calculate_hit_at_k(chunks, "Starlette 和 Pydantic", k=2) is True


def test_hit_at_k_rank_cutoff_boundary():
    """Verify that a match at rank 6 is a miss when k=5, but a hit when k=6."""
    chunks = [{"content": f"filler {i}"} for i in range(5)]
    chunks.append({"content": "target snippet hidden at rank 6"})

    # Rank 6 is index 5
    assert calculate_hit_at_k(chunks, "target snippet", k=5) is False
    assert calculate_hit_at_k(chunks, "target snippet", k=6) is True


def test_hit_at_k_all_miss():
    chunks = [{"content": "完全无关的文档内容"} for _ in range(5)]
    assert calculate_hit_at_k(chunks, "预期金色片段", k=5) is False


def test_hit_at_k_empty_inputs_and_edge_cases():
    assert calculate_hit_at_k([], "gold", k=5) is False
    assert calculate_hit_at_k([{"content": "hello"}], "", k=5) is False
    assert calculate_hit_at_k([{"content": "hello"}], "   ", k=5) is False
    assert calculate_hit_at_k([{}], "gold", k=5) is False


# ==============================================================================
# 2. Gold-snippet Citation Precision Tests
# ==============================================================================


def test_citation_precision_normal_and_partial():
    cited = [
        "包含 gold_snippet 的切片内容",
        "不包含目标片段的切片内容",
        "另一个包含 gold_snippet 的切片内容",
    ]
    precision = calculate_gold_snippet_citation_precision(cited, "gold_snippet")
    assert math.isclose(precision, 2.0 / 3.0, rel_tol=1e-5)


def test_citation_precision_all_hit():
    cited = ["片段 gold", "也是 gold"]
    assert calculate_gold_snippet_citation_precision(cited, "gold") == 1.0


def test_citation_precision_all_miss():
    cited = ["片段 a", "片段 b"]
    assert calculate_gold_snippet_citation_precision(cited, "gold") == 0.0


def test_citation_precision_empty_citations_and_zero_division():
    assert calculate_gold_snippet_citation_precision([], "gold") == 0.0
    assert calculate_gold_snippet_citation_precision(["content"], "") == 0.0
    assert calculate_gold_snippet_citation_precision(["content"], "   ") == 0.0


def test_macro_citation_precision():
    assert calculate_macro_citation_precision([1.0, 0.5, 0.0]) == 0.5
    assert calculate_macro_citation_precision([0.75]) == 0.75
    assert calculate_macro_citation_precision([]) == 0.0
    assert calculate_macro_citation_precision([0.0, 0.0]) == 0.0


# ==============================================================================
# 3. Refusal Accuracy & Rates Tests
# ==============================================================================


def test_refusal_accuracy_perfect():
    # 20 answerable not refused, 5 unanswerable refused
    records = [{"type": "answerable", "refused": False} for _ in range(20)]
    records.extend([{"type": "unanswerable", "refused": True} for _ in range(5)])

    metrics = calculate_refusal_accuracy(records)
    assert metrics["refusal_accuracy"] == 1.0
    assert metrics["unanswerable_refusal_rate"] == 1.0
    assert metrics["answerable_rejection_rate"] == 0.0


def test_refusal_accuracy_all_inverted():
    # Worst case: 20 answerable falsely rejected, 5 unanswerable wrongly accepted
    records = [{"type": "answerable", "refused": True} for _ in range(20)]
    records.extend([{"type": "unanswerable", "refused": False} for _ in range(5)])

    metrics = calculate_refusal_accuracy(records)
    assert metrics["refusal_accuracy"] == 0.0
    assert metrics["unanswerable_refusal_rate"] == 0.0
    assert metrics["answerable_rejection_rate"] == 1.0


def test_refusal_accuracy_partial():
    # 18 of 20 answerable accepted (2 false rejections)
    # 4 of 5 unanswerable refused (1 false acceptance)
    records = [{"type": "answerable", "refused": False} for _ in range(18)]
    records.extend([{"type": "answerable", "refused": True} for _ in range(2)])
    records.extend([{"type": "unanswerable", "refused": True} for _ in range(4)])
    records.extend([{"type": "unanswerable", "refused": False} for _ in range(1)])

    metrics = calculate_refusal_accuracy(records)
    # Total correct = 18 + 4 = 22 / 25 = 0.88
    assert metrics["refusal_accuracy"] == 0.88
    assert metrics["unanswerable_refusal_rate"] == 0.80
    assert metrics["answerable_rejection_rate"] == 0.10


def test_refusal_accuracy_empty_and_zero_division():
    metrics = calculate_refusal_accuracy([])
    assert metrics["refusal_accuracy"] == 0.0
    assert metrics["unanswerable_refusal_rate"] == 0.0
    assert metrics["answerable_rejection_rate"] == 0.0

    # Only answerable queries
    metrics_ans_only = calculate_refusal_accuracy([{"type": "answerable", "refused": False}])
    assert metrics_ans_only["refusal_accuracy"] == 1.0
    assert metrics_ans_only["unanswerable_refusal_rate"] == 0.0
    assert metrics_ans_only["answerable_rejection_rate"] == 0.0

    # Only unanswerable queries
    metrics_unans_only = calculate_refusal_accuracy([{"type": "unanswerable", "refused": True}])
    assert metrics_unans_only["refusal_accuracy"] == 1.0
    assert metrics_unans_only["unanswerable_refusal_rate"] == 1.0
    assert metrics_unans_only["answerable_rejection_rate"] == 0.0


# ==============================================================================
# 4. Percentile Linear Interpolation Tests
# ==============================================================================


def test_percentile_empty_and_single():
    assert calculate_percentile([], 50.0) == 0.0
    assert calculate_percentile([42.5], 0.0) == 42.5
    assert calculate_percentile([42.5], 50.0) == 42.5
    assert calculate_percentile([42.5], 95.0) == 42.5
    assert calculate_percentile([42.5], 100.0) == 42.5


def test_percentile_two_elements():
    vals = [10.0, 20.0]
    assert calculate_percentile(vals, 0.0) == 10.0
    assert calculate_percentile(vals, 50.0) == 15.0
    assert calculate_percentile(vals, 100.0) == 20.0


def test_percentile_known_25_dataset():
    """Verify linear interpolation formula on 25 elements (1..25).

    N = 25
    idx = (p / 100) * 24
    p = 50: idx = 12.0 -> value = 13.0
    p = 95: idx = 22.8 -> value = 23 + 0.8 * (24 - 23) = 23.8
    """
    vals = [float(i) for i in range(1, 26)]

    p0 = calculate_percentile(vals, 0.0)
    p50 = calculate_percentile(vals, 50.0)
    p95 = calculate_percentile(vals, 95.0)
    p100 = calculate_percentile(vals, 100.0)

    assert p0 == 1.0
    assert p50 == 13.0
    assert math.isclose(p95, 23.8, rel_tol=1e-5)
    assert p100 == 25.0


def test_percentile_identical_values():
    vals = [5.5, 5.5, 5.5, 5.5]
    assert calculate_percentile(vals, 50.0) == 5.5
    assert calculate_percentile(vals, 95.0) == 5.5


def test_percentile_clamping():
    vals = [10.0, 20.0, 30.0]
    assert calculate_percentile(vals, -10.0) == 10.0
    assert calculate_percentile(vals, 150.0) == 30.0


# ==============================================================================
# 5. Consolidation & Corpus Readiness Tests
# ==============================================================================


def test_aggregate_mode_metrics_structure():
    records = [
        {"type": "answerable", "hit_at_5": True, "citation_precision": 1.0, "refused": False, "latency_ms": 10.0},
        {"type": "answerable", "hit_at_5": False, "citation_precision": 0.0, "refused": False, "latency_ms": 20.0},
        {"type": "unanswerable", "hit_at_5": False, "citation_precision": None, "refused": True, "latency_ms": 30.0},
    ]

    summary = aggregate_mode_metrics(records, "hybrid+agent")
    assert summary["mode"] == "hybrid+agent"
    assert summary["total_queries"] == 3
    assert summary["hit_at_5"] == 0.5  # 1 of 2 answerable hit
    assert summary["citation_precision"] == 0.5  # average of 1.0 and 0.0
    assert summary["refusal_accuracy"] == 1.0  # 2 ans not refused + 1 unans refused = 3/3
    assert summary["latency_p50_ms"] == 20.0


def test_check_corpus_ready_mock():
    mock_db = MagicMock()

    # Case 1: Missing all documents
    mock_db.query().filter().all.return_value = []
    ready, missing = check_corpus_ready(mock_db, ["doc1.md", "doc2.md"])
    assert ready is False
    assert set(missing) == {"doc1.md", "doc2.md"}

    # Case 2: One document ready, one missing
    doc1 = MagicMock()
    doc1.filename = "doc1.md"
    doc1.status = "ready"
    mock_db.query().filter().all.return_value = [doc1]
    ready, missing = check_corpus_ready(mock_db, ["doc1.md", "doc2.md"])
    assert ready is False
    assert missing == ["doc2.md"]

    # Case 3: Both documents ready
    doc2 = MagicMock()
    doc2.filename = "doc2.md"
    doc2.status = "completed"
    mock_db.query().filter().all.return_value = [doc1, doc2]
    ready, missing = check_corpus_ready(mock_db, ["doc1.md", "doc2.md"])
    assert ready is True
    assert missing == []
