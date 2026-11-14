"""Tier 1: Feature Coverage E2E Tests.

Validates primary functionality and contracts across all 5 core features:
1. Document Upload (.md, .txt, .markdown, .pdf, status transitions)
2. Document List & Polling (schema validation, statuses, chunk counts, ordering)
3. Document Deletion (cascade chunk deletion, 404s, list updates)
4. Streaming Q&A SSE Protocol (headers, step progression, token delivery, citations, done)
5. Citation Reconciliation & Chunk Modal (marker matching, chunk detail, provenance)

Authoritative sources:
- apps/api/routers/documents.py
- apps/api/routers/chat.py
- docs/PRD.md Section 4, 6, 8
- apps/api/agent/citations.py
"""

import io
from unittest.mock import patch
from fastapi.testclient import TestClient

from apps.api.db.models import Chunk, Document, Run
from apps.api.db.session import SessionLocal
from apps.api.llm.provider import FakeLLMProvider
from tests.e2e.conftest import parse_sse_events, upload_test_doc

# ---------------------------------------------------------------------------
# Feature 1: Document Upload
# ---------------------------------------------------------------------------

def test_tier1_upload_markdown_file_success(client: TestClient, managed_document_ids):
    """Verify uploading a valid Markdown (.md) document returns HTTP 202 with processing status."""
    content = b"# Architecture Overview\n\nEvidenceOS uses pgvector for hybrid retrieval."
    status_code, body = upload_test_doc(client, "arch_overview.md", content, "text/markdown")

    assert status_code == 202
    assert "id" in body
    assert body["status"] == "processing"
    assert "Document uploaded" in body["message"]
    managed_document_ids.append(body["id"])


def test_tier1_upload_plaintext_file_success(client: TestClient, managed_document_ids):
    """Verify uploading a plain text (.txt) document is accepted with HTTP 202."""
    content = b"EvidenceOS plain text technical documentation notes."
    status_code, body = upload_test_doc(client, "notes.txt", content, "text/plain")

    assert status_code == 202
    assert body["status"] == "processing"
    managed_document_ids.append(body["id"])


def test_tier1_upload_alternate_markdown_extension(client: TestClient, managed_document_ids):
    """Verify uploading .markdown extension is supported with HTTP 202."""
    content = b"# Specification\n\nDetailed system specifications."
    status_code, body = upload_test_doc(client, "spec.markdown", content, "text/markdown")

    assert status_code == 202
    assert body["status"] == "processing"
    managed_document_ids.append(body["id"])


def test_tier1_upload_pdf_file_success(client: TestClient, managed_document_ids):
    """Verify uploading a PDF (.pdf) file is accepted with HTTP 202."""
    # Minimal PDF structure
    minimal_pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >> endobj\n"
        b"xref\n0 4\n0000000000 65535 f \n0000000010 00000 n \n0000000060 00000 n \n0000000117 00000 n \n"
        b"trailer << /Size 4 /Root 1 0 R >>\nstartxref\n199\n%%EOF"
    )
    status_code, body = upload_test_doc(client, "manual.pdf", minimal_pdf, "application/pdf")

    assert status_code == 202
    assert body["status"] == "processing"
    managed_document_ids.append(body["id"])


def test_tier1_upload_background_ingestion_completion(client: TestClient, managed_document_ids):
    """Verify background ingestion completes synchronously in TestClient, transitioning doc to 'ready'."""
    content = (
        b"# Hybrid Search Design\n\n"
        b"EvidenceOS combines dense vector embeddings with BM25 keyword search via jieba.\n\n"
        b"## Reciprocal Rank Fusion\n\n"
        b"RRF scores balance ranking across vector and fulltext search channels.\n"
    )
    status_code, body = upload_test_doc(client, "hybrid_design.md", content, "text/markdown")
    assert status_code == 202
    doc_id = body["id"]
    managed_document_ids.append(doc_id)

    # In TestClient, background task has already finished
    with SessionLocal() as db:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        assert doc is not None
        assert doc.status == "ready"
        assert doc.n_chunks >= 2
        assert doc.error is None


# ---------------------------------------------------------------------------
# Feature 2: Document List & Polling
# ---------------------------------------------------------------------------

def test_tier1_list_documents_empty_state(client: TestClient):
    """Verify GET /api/documents returns HTTP 200 with a list."""
    resp = client.get("/api/documents")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_tier1_list_documents_schema_validation(client: TestClient, managed_document_ids):
    """Verify GET /api/documents response adheres to DocumentResponse schema."""
    content = b"# Schema Test\n\nVerifying document list response schema fields."
    status_code, body = upload_test_doc(client, "schema_test.md", content)
    assert status_code == 202
    managed_document_ids.append(body["id"])

    resp = client.get("/api/documents")
    assert resp.status_code == 200
    docs = resp.json()
    assert len(docs) >= 1

    target = next((d for d in docs if d["id"] == body["id"]), None)
    assert target is not None
    assert target["filename"] == "schema_test.md"
    assert target["status"] in ["ready", "processing", "failed"]
    assert isinstance(target["n_chunks"], int)
    assert "created_at" in target


def test_tier1_list_documents_status_ready(client: TestClient, managed_document_ids):
    """Verify document list shows 'ready' status for successfully ingested document."""
    content = b"# Document Ready Test\n\nThis document is cleanly parsed into chunks."
    _, body = upload_test_doc(client, "ready_test.md", content)
    managed_document_ids.append(body["id"])

    resp = client.get("/api/documents")
    docs = resp.json()
    target = next(d for d in docs if d["id"] == body["id"])
    assert target["status"] == "ready"
    assert target["n_chunks"] >= 1


def test_tier1_list_documents_chunk_count_accuracy(client: TestClient, managed_document_ids):
    """Verify document list n_chunks matches actual chunk count in database."""
    content = (
        b"# Section 1\n\nContent for section 1.\n\n"
        b"# Section 2\n\nContent for section 2.\n\n"
        b"# Section 3\n\nContent for section 3.\n"
    )
    _, body = upload_test_doc(client, "chunks_count.md", content)
    doc_id = body["id"]
    managed_document_ids.append(doc_id)

    resp = client.get("/api/documents")
    target = next(d for d in resp.json() if d["id"] == doc_id)

    with SessionLocal() as db:
        actual_chunks = db.query(Chunk).filter(Chunk.document_id == doc_id).count()
        assert target["n_chunks"] == actual_chunks
        assert actual_chunks >= 3


def test_tier1_list_documents_ordering_desc(client: TestClient, managed_document_ids):
    """Verify GET /api/documents returns documents ordered by created_at descending."""
    _, doc1 = upload_test_doc(client, "first_doc.md", b"First doc content.")
    _, doc2 = upload_test_doc(client, "second_doc.md", b"Second doc content.")
    managed_document_ids.extend([doc1["id"], doc2["id"]])

    resp = client.get("/api/documents")
    docs = resp.json()
    ids = [d["id"] for d in docs]

    idx1 = ids.index(doc1["id"])
    idx2 = ids.index(doc2["id"])
    # second_doc was uploaded after first_doc, so idx2 should precede idx1
    assert idx2 < idx1


# ---------------------------------------------------------------------------
# Feature 3: Document Deletion
# ---------------------------------------------------------------------------

def test_tier1_delete_document_success(client: TestClient):
    """Verify DELETE /api/documents/{id} returns HTTP 200 with success message."""
    _, body = upload_test_doc(client, "to_delete.md", b"# To Delete\n\nContent.")
    doc_id = body["id"]

    resp = client.delete(f"/api/documents/{doc_id}")
    assert resp.status_code == 200
    assert resp.json() == {"message": "Document deleted successfully"}


def test_tier1_delete_document_cascade_chunks(client: TestClient):
    """Verify deleting a document cascades to delete all associated chunks."""
    content = b"# Cascade Test\n\nChunk 1 content.\n\n## Sub\n\nChunk 2 content."
    _, body = upload_test_doc(client, "cascade.md", content)
    doc_id = body["id"]

    # Retrieve chunk ids before deletion
    with SessionLocal() as db:
        chunk_ids = [c.id for c in db.query(Chunk).filter(Chunk.document_id == doc_id).all()]
        assert len(chunk_ids) >= 1

    # Delete document
    del_resp = client.delete(f"/api/documents/{doc_id}")
    assert del_resp.status_code == 200

    # Verify chunks are deleted
    with SessionLocal() as db:
        remaining = db.query(Chunk).filter(Chunk.document_id == doc_id).all()
        assert len(remaining) == 0

    # Also verify GET /api/chunks/{id} returns 404 for deleted chunk
    for c_id in chunk_ids:
        chunk_resp = client.get(f"/api/chunks/{c_id}")
        assert chunk_resp.status_code == 404


def test_tier1_delete_document_removed_from_list(client: TestClient):
    """Verify deleted document is immediately absent from GET /api/documents list."""
    _, body = upload_test_doc(client, "immediate_removal.md", b"Content.")
    doc_id = body["id"]

    # Verify present
    assert any(d["id"] == doc_id for d in client.get("/api/documents").json())

    # Delete
    client.delete(f"/api/documents/{doc_id}")

    # Verify absent
    assert not any(d["id"] == doc_id for d in client.get("/api/documents").json())


def test_tier1_delete_document_nonexistent_returns_404(client: TestClient):
    """Verify deleting a non-existent document UUID returns HTTP 404."""
    resp = client.delete("/api/documents/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Document not found"


def test_tier1_delete_document_idempotency_failure(client: TestClient):
    """Verify deleting an already deleted document returns HTTP 404."""
    _, body = upload_test_doc(client, "idempotent.md", b"Content.")
    doc_id = body["id"]

    resp1 = client.delete(f"/api/documents/{doc_id}")
    assert resp1.status_code == 200

    resp2 = client.delete(f"/api/documents/{doc_id}")
    assert resp2.status_code == 404


# ---------------------------------------------------------------------------
# Feature 4: Streaming Q&A SSE Protocol
# ---------------------------------------------------------------------------

MOCK_DOC_CONTENT = (
    b"# FastAPI Dependency Injection\n\n"
    b"FastAPI provides a powerful Dependency Injection system using Depends().\n\n"
    b"## Scopes\n\n"
    b"Dependencies can be scoped to individual routes or router levels.\n"
)

def test_tier1_chat_sse_headers_contract(client: TestClient, managed_document_ids):
    """Verify POST /api/chat responds with standard SSE streaming headers."""
    _, body = upload_test_doc(client, "fastapi_di.md", MOCK_DOC_CONTENT)
    managed_document_ids.append(body["id"])

    resp = client.post("/api/chat", json={"question": "FastAPI 如何做依赖注入？"})
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    assert "no-cache" in resp.headers["cache-control"]
    assert resp.headers.get("x-accel-buffering") == "no"


def test_tier1_chat_sse_step_event_progression(client: TestClient, managed_document_ids):
    """Verify step events sequence: retrieve -> grade -> generate -> verify_citations."""
    _, body = upload_test_doc(client, "fastapi_di.md", MOCK_DOC_CONTENT)
    managed_document_ids.append(body["id"])

    fake_llm = FakeLLMProvider(
        custom_grades=[{"sufficient": True, "reason": "文档内容充分", "missing": ""}],
        custom_answers=["FastAPI 原生支持依赖注入 [1]。"],
    )

    with patch("apps.api.routers.chat.get_llm_provider", return_value=fake_llm):
        resp = client.post("/api/chat", json={"question": "FastAPI 如何做依赖注入？"})
        assert resp.status_code == 200
        events = parse_sse_events(resp.text)

        step_events = [e[1] for e in events if e[0] == "step"]
        assert len(step_events) >= 4

        # First step is bootstrap retrieve
        assert step_events[0]["node"] == "retrieve"
        assert step_events[0]["status"] == "running"

        completed_nodes = [s["node"] for s in step_events if s.get("status") == "completed"]
        assert "retrieve" in completed_nodes
        assert "grade" in completed_nodes
        assert "generate" in completed_nodes
        assert "verify_citations" in completed_nodes


def test_tier1_chat_sse_token_delivery(client: TestClient, managed_document_ids):
    """Verify answer tokens are pushed via token events and reconstruct verified answer."""
    _, body = upload_test_doc(client, "fastapi_di.md", MOCK_DOC_CONTENT)
    managed_document_ids.append(body["id"])

    expected_answer = "FastAPI 提供了强大的依赖注入系统 [1]。"
    fake_llm = FakeLLMProvider(
        custom_grades=[{"sufficient": True, "reason": "充分", "missing": ""}],
        custom_answers=[expected_answer],
    )

    with patch("apps.api.routers.chat.get_llm_provider", return_value=fake_llm):
        resp = client.post("/api/chat", json={"question": "FastAPI 如何做依赖注入？"})
        assert resp.status_code == 200
        events = parse_sse_events(resp.text)

        token_events = [e[1]["text"] for e in events if e[0] == "token"]
        assert len(token_events) > 0
        reconstructed = "".join(token_events)
        assert reconstructed == expected_answer


def test_tier1_chat_sse_citations_event_contract(client: TestClient, managed_document_ids):
    """Verify citations event contains non-empty items with full provenance metadata."""
    _, body = upload_test_doc(client, "fastapi_di.md", MOCK_DOC_CONTENT)
    managed_document_ids.append(body["id"])

    fake_llm = FakeLLMProvider(
        custom_grades=[{"sufficient": True, "reason": "充分", "missing": ""}],
        custom_answers=["FastAPI 通过 Depends 声明依赖 [1]。"],
    )

    with patch("apps.api.routers.chat.get_llm_provider", return_value=fake_llm):
        resp = client.post("/api/chat", json={"question": "FastAPI 依赖注入？"})
        assert resp.status_code == 200
        events = parse_sse_events(resp.text)

        citation_events = [e[1] for e in events if e[0] == "citations"]
        assert len(citation_events) == 1
        items = citation_events[0]["items"]
        assert len(items) >= 1
        citation = items[0]
        assert citation["n"] == 1
        assert "chunk_id" in citation
        assert isinstance(citation["document"], str) and len(citation["document"]) > 0
        assert citation["document"].endswith((".md", ".txt", ".pdf", ".markdown"))
        assert "snippet" in citation
        assert len(citation["snippet"]) > 0


def test_tier1_chat_sse_done_event_metadata(client: TestClient, managed_document_ids):
    """Verify done event delivers run_id, refused flag, and positive latency_ms."""
    _, body = upload_test_doc(client, "fastapi_di.md", MOCK_DOC_CONTENT)
    managed_document_ids.append(body["id"])

    fake_llm = FakeLLMProvider(
        custom_grades=[{"sufficient": True, "reason": "充分", "missing": ""}],
        custom_answers=["FastAPI 依赖注入简单直观 [1]。"],
    )

    with patch("apps.api.routers.chat.get_llm_provider", return_value=fake_llm):
        resp = client.post("/api/chat", json={"question": "FastAPI 依赖注入？"})
        events = parse_sse_events(resp.text)

        done_events = [e[1] for e in events if e[0] == "done"]
        assert len(done_events) == 1
        done = done_events[0]
        assert "run_id" in done
        assert done["refused"] is False
        assert done["latency_ms"] > 0


# ---------------------------------------------------------------------------
# Feature 5: Citation Reconciliation & Chunk Modal
# ---------------------------------------------------------------------------

def test_tier1_citation_reconciliation_marker_match(client: TestClient, managed_document_ids):
    """Verify [1] citation marker in answer matches items[0] with n=1."""
    _, body = upload_test_doc(client, "fastapi_di.md", MOCK_DOC_CONTENT)
    managed_document_ids.append(body["id"])

    fake_llm = FakeLLMProvider(
        custom_grades=[{"sufficient": True, "reason": "充分", "missing": ""}],
        custom_answers=["根据文档 [1]，FastAPI 依赖注入机制高效。"],
    )

    with patch("apps.api.routers.chat.get_llm_provider", return_value=fake_llm):
        resp = client.post("/api/chat", json={"question": "FastAPI 依赖注入？"})
        events = parse_sse_events(resp.text)

        citations = next(e[1]["items"] for e in events if e[0] == "citations")
        assert len(citations) >= 1
        assert citations[0]["n"] == 1


def test_tier1_chunk_modal_fetch_detail_success(client: TestClient, managed_document_ids):
    """Verify GET /api/chunks/{id} returns ChunkDetailResponse with full content."""
    content = b"# Section Header\n\nSpecific detailed chunk text for modal display."
    _, body = upload_test_doc(client, "modal_test.md", content)
    managed_document_ids.append(body["id"])

    with SessionLocal() as db:
        chunk = db.query(Chunk).filter(Chunk.document_id == body["id"]).first()
        assert chunk is not None
        chunk_id = chunk.id

    resp = client.get(f"/api/chunks/{chunk_id}")
    assert resp.status_code == 200
    detail = resp.json()

    assert detail["id"] == chunk_id
    assert detail["document_id"] == body["id"]
    assert detail["document"] == "modal_test.md"
    assert detail["idx"] == 0
    assert "Section Header" in detail["heading"]
    assert "Specific detailed chunk text" in detail["content"]


def test_tier1_chunk_modal_content_verbatim_match(client: TestClient, managed_document_ids):
    """Verify ChunkModal detail content contains citation snippet verbatim."""
    _, body = upload_test_doc(client, "fastapi_di.md", MOCK_DOC_CONTENT)
    managed_document_ids.append(body["id"])

    fake_llm = FakeLLMProvider(
        custom_grades=[{"sufficient": True, "reason": "充分", "missing": ""}],
        custom_answers=["FastAPI 依赖注入系统 [1]。"],
    )

    with patch("apps.api.routers.chat.get_llm_provider", return_value=fake_llm):
        resp = client.post("/api/chat", json={"question": "FastAPI 依赖注入？"})
        events = parse_sse_events(resp.text)
        citations = next(e[1]["items"] for e in events if e[0] == "citations")
        target_chunk_id = citations[0]["chunk_id"]
        snippet = citations[0]["snippet"]

    chunk_resp = client.get(f"/api/chunks/{target_chunk_id}")
    assert chunk_resp.status_code == 200
    chunk_detail = chunk_resp.json()

    # The snippet must match the beginning of or exist verbatim in chunk content
    assert chunk_detail["content"].startswith(snippet[:50])


def test_tier1_chunk_modal_nonexistent_chunk_404(client: TestClient):
    """Verify GET /api/chunks/{id} with non-existent ID returns HTTP 404."""
    resp = client.get("/api/chunks/nonexistent-chunk-uuid")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Chunk not found"


def test_tier1_chunk_modal_page_and_heading_metadata(client: TestClient, managed_document_ids):
    """Verify chunk metadata includes valid idx and heading hierarchy."""
    content = b"# Main Title\n\nParagraph 1.\n\n## Sub Title\n\nParagraph 2."
    _, body = upload_test_doc(client, "metadata_test.md", content)
    managed_document_ids.append(body["id"])

    with SessionLocal() as db:
        chunks = db.query(Chunk).filter(Chunk.document_id == body["id"]).order_by(Chunk.idx.asc()).all()
        assert len(chunks) >= 2
        first_chunk_id = chunks[0].id
        second_chunk_id = chunks[1].id

    c1 = client.get(f"/api/chunks/{first_chunk_id}").json()
    c2 = client.get(f"/api/chunks/{second_chunk_id}").json()

    assert c1["idx"] == 0
    assert c2["idx"] == 1
    assert "Main Title" in c1["heading"]
    assert "Sub Title" in c2["heading"]
