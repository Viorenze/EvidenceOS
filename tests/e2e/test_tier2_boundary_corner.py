"""Tier 2: Boundary & Corner Cases E2E Tests.

Validates defensive engineering, boundary conditions, and adversarial inputs:
1. Document Upload Boundaries (0-byte, invalid extensions, missing fields, special characters, whitespace)
2. Document List & Polling Boundaries (rapid consecutive polling, Unicode/CJK filenames, failed ingestion state, mixed statuses)
3. Document Deletion Boundaries (malformed UUIDs, SQL injection payloads, path traversal payloads, zero-chunk deletion, concurrent deletion)
4. Streaming Q&A Boundaries & Corner Cases (empty/whitespace queries, unanswerable refusal stream, refusal citations/done payload, DB error stream termination)
5. Citation Reconciliation Boundaries & Protection (subscript immunity `data[0]`, fenced code shielding, inline code shielding, Chinese full-width normalization, dangling marker stripping)

Authoritative sources:
- apps/api/routers/documents.py
- apps/api/routers/chat.py
- apps/api/agent/citations.py
- docs/PRD.md Section 6, 8
- AGENTS.md Rules 6, 7
"""

import io
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from apps.api.config import get_settings
from apps.api.db.models import Chunk, Document
from apps.api.db.session import SessionLocal
from apps.api.llm.provider import FakeLLMProvider
from apps.api.agent.citations import extract_citation_numbers, verify_citations, clean_answer_citations
from tests.e2e.conftest import parse_sse_events, upload_test_doc

# ---------------------------------------------------------------------------
# Feature 1: Document Upload Boundaries
# ---------------------------------------------------------------------------

def test_tier2_upload_empty_zero_byte_file(client: TestClient):
    """Verify uploading a 0-byte file returns HTTP 400 'Uploaded file is empty.'"""
    files = {"file": ("empty.md", io.BytesIO(b""), "text/markdown")}
    resp = client.post("/api/documents", files=files)

    assert resp.status_code == 400
    assert "Uploaded file is empty" in resp.json()["detail"]


def test_tier2_upload_unsupported_binary_extension(client: TestClient):
    """Verify uploading an executable (.exe) returns HTTP 400 unsupported format."""
    files = {"file": ("payload.exe", io.BytesIO(b"MZ\x90\x00Binary"), "application/octet-stream")}
    resp = client.post("/api/documents", files=files)

    assert resp.status_code == 400
    assert "Unsupported format" in resp.json()["detail"]


def test_tier2_upload_unsupported_json_extension(client: TestClient):
    """Verify uploading .json file returns HTTP 400 unsupported format."""
    files = {"file": ("data.json", io.BytesIO(b'{"key": "value"}'), "application/json")}
    resp = client.post("/api/documents", files=files)

    assert resp.status_code == 400
    assert "Unsupported format" in resp.json()["detail"]


def test_tier2_upload_missing_file_field(client: TestClient):
    """Verify POST /api/documents without 'file' field returns HTTP 422 Unprocessable Entity."""
    resp = client.post("/api/documents", data={"other_field": "test"})
    assert resp.status_code == 422


def test_tier2_upload_special_characters_filename(client: TestClient, managed_document_ids):
    """Verify uploading document with spaces, symbols, and brackets in filename succeeds."""
    filename = "#doc & report (v2) [draft] @test!.md"
    content = b"# Special Name Doc\n\nTesting special character tolerance in filename."
    status_code, body = upload_test_doc(client, filename, content)

    assert status_code == 202
    managed_document_ids.append(body["id"])

    # Verify preserved in database
    with SessionLocal() as db:
        doc = db.query(Document).filter(Document.id == body["id"]).first()
        assert doc is not None
        assert doc.filename == filename


# ---------------------------------------------------------------------------
# Feature 2: Document List & Polling Boundaries
# ---------------------------------------------------------------------------

def test_tier2_list_rapid_consecutive_polling(client: TestClient):
    """Verify rapid consecutive document listing calls succeed consistently without connection pool exhaustion."""
    for _ in range(10):
        resp = client.get("/api/documents")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


def test_tier2_list_unicode_cjk_filename(client: TestClient, managed_document_ids):
    """Verify documents with CJK / Chinese characters in filename preserve exact Unicode strings."""
    filename = "深度学习架构与混合检索技术规范_2026.md"
    content = b"# \xe4\xb8\xad\xe6\x96\x87\xe6\xa0\x87\xe9\xa2\x98\n\n\xe6\xb5\x8b\xe8\xaf\x95\xe5\x86\x85\xe5\xae\xb9\xe3\x80\x82"
    status_code, body = upload_test_doc(client, filename, content)
    assert status_code == 202
    managed_document_ids.append(body["id"])

    resp = client.get("/api/documents")
    target = next((d for d in resp.json() if d["id"] == body["id"]), None)
    assert target is not None
    assert target["filename"] == filename


def test_tier2_list_failed_document_error_reporting(client: TestClient, managed_document_ids):
    """Verify document in failed state correctly populates status='failed' and error field."""
    # Insert a document explicitly marked as failed
    failed_id = "failed-doc-tier2-test"
    with SessionLocal() as db:
        doc = Document(
            id=failed_id,
            filename="corrupt_spec.pdf",
            status="failed",
            n_chunks=0,
            error="PDF parsing failed: stream decoding error",
        )
        db.add(doc)
        db.commit()
    managed_document_ids.append(failed_id)

    resp = client.get("/api/documents")
    target = next(d for d in resp.json() if d["id"] == failed_id)
    assert target["status"] == "failed"
    assert "PDF parsing failed" in target["error"]


def test_tier2_list_mixed_document_statuses(client: TestClient, managed_document_ids):
    """Verify document list accurately displays mixed ready, processing, and failed statuses."""
    with SessionLocal() as db:
        d_ready = Document(id="doc-ready-t2", filename="ready.md", status="ready", n_chunks=3)
        d_proc = Document(id="doc-proc-t2", filename="proc.md", status="processing", n_chunks=0)
        d_fail = Document(id="doc-fail-t2", filename="fail.md", status="failed", n_chunks=0, error="Corrupt")
        db.add_all([d_ready, d_proc, d_fail])
        db.commit()
    managed_document_ids.extend(["doc-ready-t2", "doc-proc-t2", "doc-fail-t2"])

    resp = client.get("/api/documents")
    docs_by_id = {d["id"]: d for d in resp.json()}

    assert docs_by_id["doc-ready-t2"]["status"] == "ready"
    assert docs_by_id["doc-proc-t2"]["status"] == "processing"
    assert docs_by_id["doc-fail-t2"]["status"] == "failed"


def test_tier2_list_large_chunk_count_document(client: TestClient, managed_document_ids):
    """Verify document resulting in 10+ chunks serializes without truncation."""
    sections = [f"# Heading {i}\n\nDetailed content for section {i}." for i in range(12)]
    content = "\n\n".join(sections).encode("utf-8")

    status_code, body = upload_test_doc(client, "large_corpus.md", content)
    assert status_code == 202
    managed_document_ids.append(body["id"])

    resp = client.get("/api/documents")
    target = next(d for d in resp.json() if d["id"] == body["id"])
    assert target["n_chunks"] >= 10


# ---------------------------------------------------------------------------
# Feature 3: Document Deletion Boundaries
# ---------------------------------------------------------------------------

def test_tier2_delete_malformed_non_uuid_id(client: TestClient):
    """Verify DELETE /api/documents/not-a-uuid returns HTTP 404 without server exception."""
    resp = client.delete("/api/documents/invalid_format_id_12345")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Document not found"


def test_tier2_delete_sql_injection_payload(client: TestClient):
    """Verify DELETE with SQL injection string returns 404 safely without database error."""
    payload = "1' OR '1'='1"
    resp = client.delete(f"/api/documents/{payload}")
    assert resp.status_code == 404


def test_tier2_delete_path_traversal_payload(client: TestClient):
    """Verify DELETE with directory traversal path returns 404."""
    payload = "../../etc/passwd"
    resp = client.delete(f"/api/documents/{payload}")
    assert resp.status_code == 404


def test_tier2_delete_document_with_zero_chunks(client: TestClient, managed_document_ids):
    """Verify deleting a document that has 0 chunks completes cleanly with 200 OK."""
    doc_id = "doc-zero-chunks-t2"
    with SessionLocal() as db:
        doc = Document(id=doc_id, filename="empty_sections.md", status="ready", n_chunks=0)
        db.add(doc)
        db.commit()

    del_resp = client.delete(f"/api/documents/{doc_id}")
    assert del_resp.status_code == 200
    assert del_resp.json() == {"message": "Document deleted successfully"}


def test_tier2_delete_concurrent_rapid_deletion(client: TestClient):
    """Verify two consecutive delete requests on same doc: first returns 200, second returns 404."""
    _, body = upload_test_doc(client, "rapid_delete.md", b"Content.")
    doc_id = body["id"]

    r1 = client.delete(f"/api/documents/{doc_id}")
    r2 = client.delete(f"/api/documents/{doc_id}")

    assert r1.status_code == 200
    assert r2.status_code == 404


# ---------------------------------------------------------------------------
# Feature 4: Streaming Q&A Boundaries & Corner Cases
# ---------------------------------------------------------------------------

def test_tier2_chat_empty_question_rejected(client: TestClient):
    """Verify empty question string returns HTTP 422 before starting SSE stream."""
    resp = client.post("/api/chat", json={"question": ""})
    assert resp.status_code == 422
    assert "Question cannot be empty" in resp.json()["detail"]


def test_tier2_chat_whitespace_question_rejected(client: TestClient):
    """Verify whitespace-only question string returns HTTP 422 before starting SSE stream."""
    resp = client.post("/api/chat", json={"question": "   \n\t   "})
    assert resp.status_code == 422
    assert "Question cannot be empty" in resp.json()["detail"]


def test_tier2_chat_unanswerable_refusal_stream(client: TestClient):
    """Verify unanswerable question triggers rewrite loops and streams fixed refusal text."""
    # Empty search results trigger grade insufficient -> rewrite -> refuse
    with patch("apps.api.agent.nodes.hybrid_search", return_value=[]):
        resp = client.post("/api/chat", json={"question": "如何烹饪正宗法式鹅肝？"})
        assert resp.status_code == 200
        events = parse_sse_events(resp.text)

        step_nodes = [e[1]["node"] for e in events if e[0] == "step"]
        assert "refuse" in step_nodes

        token_events = [e[1]["text"] for e in events if e[0] == "token"]
        streamed_answer = "".join(token_events)
        assert streamed_answer == "根据已有知识库内容，无法回答该问题。"


def test_tier2_chat_refusal_citations_and_done_payload(client: TestClient):
    """Verify refusal stream delivers empty citations array and done event with refused=true."""
    with patch("apps.api.agent.nodes.hybrid_search", return_value=[]):
        resp = client.post("/api/chat", json={"question": "火星探测器推进剂化学配比？"})
        events = parse_sse_events(resp.text)

        citations_events = [e[1] for e in events if e[0] == "citations"]
        assert len(citations_events) == 1
        assert citations_events[0]["items"] == []

        done_events = [e[1] for e in events if e[0] == "done"]
        assert len(done_events) == 1
        assert done_events[0]["refused"] is True


def test_tier2_chat_db_persistence_failure_emits_error_no_done(client: TestClient):
    """Verify database persistence failure emits 'error' event and NEVER emits 'done' event."""
    mock_chunks = [
        {
            "chunk_id": "c1",
            "document_id": "d1",
            "document": "doc.md",
            "page": 1,
            "heading": "H",
            "content": "Content",
            "rrf_score": 0.05,
        }
    ]
    fake_llm = FakeLLMProvider(
        custom_grades=[{"sufficient": True, "reason": "ok", "missing": ""}],
        custom_answers=["回答 [1]。"],
    )

    from apps.api.main import app
    from apps.api.db.session import get_db

    mock_db = MagicMock()
    mock_db.commit.side_effect = Exception("Disk quota exceeded")
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        with patch("apps.api.routers.chat.get_llm_provider", return_value=fake_llm), \
             patch("apps.api.agent.nodes.hybrid_search", return_value=mock_chunks):
            resp = client.post("/api/chat", json={"question": "测试持久化异常？"})
            assert resp.status_code == 200
            events = parse_sse_events(resp.text)

            event_names = [e[0] for e in events]
            assert "error" in event_names
            assert "done" not in event_names

            error_data = next(e[1] for e in events if e[0] == "error")
            assert "Database persistence failed" in error_data["message"]
    finally:
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Feature 5: Citation Reconciliation Boundaries & Protection
# ---------------------------------------------------------------------------

def test_tier2_citation_subscript_immunity():
    """Verify array subscripts like data[0], arr[1], items[10] are NOT extracted as citations."""
    code_text = "在 Python 中，通过 data[0] 获取首个元素，arr[1] 获取次元素，以及 items[10] 访问列表项。"
    citations = extract_citation_numbers(code_text)
    assert citations == []


def test_tier2_citation_fenced_code_block_shielding():
    """Verify fenced code blocks shield enclosed bracketed numbers from citation parsing."""
    markdown_text = (
        "说明文档如下：\n"
        "```python\n"
        "# 示例代码 [1] 和 [2]\n"
        "val = items[0]\n"
        "```\n"
        "这是真实的参考结论 [1]。"
    )
    citations = extract_citation_numbers(markdown_text)
    # Only the prose [1] outside the code block should be extracted
    assert citations == [1]


def test_tier2_citation_inline_code_shielding():
    """Verify inline code `arr[1]` or `[1]` shields bracketed numbers from citation parsing."""
    text = "使用 `config[1]` 配置项，在生产环境中运行 [1]。"
    citations = extract_citation_numbers(text)
    assert citations == [1]


def test_tier2_citation_chinese_fullwidth_brackets_normalization():
    """Verify Chinese full-width brackets 【1】 and grouped 【1, 2】 are normalized to numbers."""
    text = "根据技术规范【1】，以及系统架构【2】，支持该特性【1, 2】。"
    citations = extract_citation_numbers(text)
    assert citations == [1, 2]


def test_tier2_citation_dangling_out_of_range_cleaned():
    """Verify out-of-range citations like [99] are stripped from prose text."""
    chunks = [
        {"chunk_id": "c1", "document": "doc1.md", "page": 1, "heading": "H1", "content": "Text 1"}
    ]
    # Model hallucinated [99] when only 1 chunk exists
    raw_answer = "系统架构已支持分布式部署 [1]，另外还支持自动化扩缩容 [99]。"
    verified, valid_items, is_valid = verify_citations(raw_answer, chunks)

    # clean_answer_citations requires a Set[int] of valid citation numbers
    valid_numbers = {item["n"] for item in valid_items}
    cleaned = clean_answer_citations(raw_answer, valid_numbers)
    assert "[1]" in cleaned
    assert "[99]" not in cleaned
    assert is_valid is True
    assert len(valid_items) == 1
