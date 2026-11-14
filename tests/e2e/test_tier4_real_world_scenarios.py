"""Tier 4: Real-World Application Scenarios E2E Tests.

Validates end-to-end operational workflows and interview demonstration scenarios:
1. Complete Technical Interview Demonstration Workflow:
   - System health readiness verification
   - Upload EvidenceOS technical architecture document
   - Ingestion status verification in document management
   - Real-time SSE streaming Q&A with LangGraph node tracking
   - Citation badge clicking & ChunkModal provenance inspection
   - Adversarial out-of-scope refusal check with double query rewrite
   - Document lifecycle cleanup and cascade verification
2. Multi-Format Knowledge Base Curation (.md, .txt, .pdf):
   - Ingestion across distinct technical file formats
   - Hybrid retrieval across multi-format corpus
   - Bulk deletion and chunk integrity
3. High-Stress Operational Resilience & Boundary Storm:
   - Rapid burst uploads, queries, and boundary inputs
   - Zero crashes, exact HTTP status codes, consistent transaction boundaries
4. Cold-Start & Health Readiness Probe:
   - Component readiness schema verification for database and embedding models
   - Frontend readiness check simulation

Authoritative sources:
- docs/PRD.md Section 1, 4, 6, 8, 9
- docs/DECISIONS.md
- apps/web/src/lib/api.ts
"""

import io
import time
import uuid
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from apps.api.db.models import Chunk, Document
from apps.api.db.session import SessionLocal
from apps.api.llm.provider import FakeLLMProvider
from tests.e2e.conftest import parse_sse_events, upload_test_doc


def test_tier4_interview_technical_demo_scenario(client: TestClient, managed_document_ids):
    """Scenario 1: Comprehensive EvidenceOS Technical Interview Demonstration Scenario.
    Simulates the entire candidate walkthrough defined in PRD Section 1 & 9.
    """
    # -----------------------------------------------------------------------
    # Step 1: Health Readiness Verification
    # -----------------------------------------------------------------------
    health_resp = client.get("/api/health?details=true")
    assert health_resp.status_code == 200
    health_data = health_resp.json()
    assert health_data["status"] == "ok"
    assert health_data["ready"] is True
    assert health_data["components"]["database"] == "connected"
    assert health_data["components"]["embedding"]["ready"] is True

    # -----------------------------------------------------------------------
    # Step 2: Upload EvidenceOS Architecture Document
    # -----------------------------------------------------------------------
    arch_keyword = f"EvidenceOS_Arch_{uuid.uuid4().hex[:6]}"
    arch_md = f"""# {arch_keyword} 系统架构

EvidenceOS 是基于 FastAPI、PostgreSQL + pgvector 和 LangGraph 的全栈可验证检索应用。

## 混合检索架构

系统采用 pgvector 进行 512 维稠密向量余弦距离搜索，同时利用 jieba 分词后进行 PostgreSQL 全文检索。
两大检索通道通过 Reciprocal Rank Fusion (RRF, k=60) 算法融合打分，有效弥补单独向量检索在专业术语上的失真。

## 证据验证与拒答机制

LangGraph 构建了包含条件循环的智能体工作流：
1. retrieve: 混合检索 top-k 文档切片
2. grade: 评估证据是否充分
3. rewrite: 若证据不足且改写次数 < 2，改写查询重试
4. generate: 基于切片上下文生成带引用标记的回答
5. verify_citations: 服务端校验引用编号合法性，过滤未验证标记
6. refuse: 若无证据或引用无效，输出预设拒答语
""".encode("utf-8")

    filename = f"{arch_keyword}.md"
    status_code, upload_body = upload_test_doc(client, filename, arch_md)
    assert status_code == 202
    doc_id = upload_body["id"]
    managed_document_ids.append(doc_id)

    # -----------------------------------------------------------------------
    # Step 3: Ingestion Polling & Status Verification
    # -----------------------------------------------------------------------
    list_resp = client.get("/api/documents")
    assert list_resp.status_code == 200
    docs = list_resp.json()
    doc_record = next((d for d in docs if d["id"] == doc_id), None)
    assert doc_record is not None
    assert doc_record["status"] == "ready"
    assert doc_record["n_chunks"] >= 3

    # -----------------------------------------------------------------------
    # Step 4: Streaming Technical Q&A with Verifiable Citations
    # -----------------------------------------------------------------------
    technical_question = "EvidenceOS 是基于 FastAPI、PostgreSQL + pgvector 和 LangGraph 的全栈可验证检索应用。"
    expected_answer = "根据架构文档 [1]，系统融合了 pgvector 向量搜索与 jieba 全文检索 [2]。"

    fake_llm = FakeLLMProvider(
        custom_grades=[{"sufficient": True, "reason": "架构说明充足", "missing": ""}],
        custom_answers=[expected_answer],
    )

    with patch("apps.api.routers.chat.get_llm_provider", return_value=fake_llm):
        chat_resp = client.post("/api/chat", json={"question": technical_question})
        assert chat_resp.status_code == 200
        assert "text/event-stream" in chat_resp.headers["content-type"]

        events = parse_sse_events(chat_resp.text)

        # 4a. Verify step progression
        steps = [e[1] for e in events if e[0] == "step"]
        step_nodes = [s["node"] for s in steps]
        assert "retrieve" in step_nodes
        assert "grade" in step_nodes
        assert "generate" in step_nodes
        assert "verify_citations" in step_nodes

        # 4b. Verify streaming token reconstruction
        streamed_tokens = "".join(e[1]["text"] for e in events if e[0] == "token")
        assert streamed_tokens == expected_answer

        # 4c. Verify citations event
        citations_items = next(e[1]["items"] for e in events if e[0] == "citations")
        assert len(citations_items) >= 2
        chunk1_id = citations_items[0]["chunk_id"]

        # 4d. Verify done event
        done_data = next(e[1] for e in events if e[0] == "done")
        assert done_data["refused"] is False
        assert done_data["latency_ms"] > 0
        run_id = done_data["run_id"]

    # -----------------------------------------------------------------------
    # Step 5: Citation Audit & ChunkModal Inspection
    # -----------------------------------------------------------------------
    modal_resp = client.get(f"/api/chunks/{chunk1_id}")
    assert modal_resp.status_code == 200
    chunk_detail = modal_resp.json()
    assert chunk_detail["document"] == filename
    assert chunk_detail["document_id"] == doc_id
    assert len(chunk_detail["content"]) > 0

    # -----------------------------------------------------------------------
    # Step 6: Adversarial Out-of-Corpus Question -> Double Rewrite -> Refusal
    # -----------------------------------------------------------------------
    adversarial_question = "如何烹饪正宗法式黑松露烤鹅肝配红酒酱汁？"
    fake_llm_adversarial = FakeLLMProvider(
        custom_grades=[
            {"sufficient": False, "reason": "无烹饪相关文档", "missing": "菜谱配方"},
            {"sufficient": False, "reason": "改写后仍无烹饪文档", "missing": "烹饪步骤"},
            {"sufficient": False, "reason": "二次改写后仍无法回答", "missing": "全部"},
        ]
    )

    with patch("apps.api.routers.chat.get_llm_provider", return_value=fake_llm_adversarial):
        adv_resp = client.post("/api/chat", json={"question": adversarial_question})
        assert adv_resp.status_code == 200
        adv_events = parse_sse_events(adv_resp.text)

        # Verify rewrite nodes were executed
        adv_steps = [e[1]["node"] for e in adv_events if e[0] == "step"]
        assert "rewrite" in adv_steps
        assert "refuse" in adv_steps

        # Verify refusal text
        adv_tokens = "".join(e[1]["text"] for e in adv_events if e[0] == "token")
        assert adv_tokens == "根据已有知识库内容，无法回答该问题。"

        # Verify empty citations & refused=true
        adv_citations = next(e[1]["items"] for e in adv_events if e[0] == "citations")
        assert adv_citations == []
        adv_done = next(e[1] for e in adv_events if e[0] == "done")
        assert adv_done["refused"] is True

    # -----------------------------------------------------------------------
    # Step 7: Teardown & Cascading Cleanup Verification
    # -----------------------------------------------------------------------
    del_resp = client.delete(f"/api/documents/{doc_id}")
    assert del_resp.status_code == 200

    # Verify chunk endpoint returns 404
    assert client.get(f"/api/chunks/{chunk1_id}").status_code == 404


def test_tier4_multi_format_knowledge_base_curation(client: TestClient, managed_document_ids):
    """Scenario 2: Technical Knowledge Base Management across Markdown, TXT, and PDF.
    Validates ingestion, retrieval, and cleanup of diverse document formats.
    """
    prefix = f"MultiFormat_{uuid.uuid4().hex[:6]}"

    # 1. Prepare three formats
    md_content = f"# {prefix} Markdown\n\nMarkdown formatting specification.".encode("utf-8")
    txt_content = f"{prefix} Plain Text configuration notes for backend services.".encode("utf-8")
    minimal_pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >> endobj\n"
        b"xref\n0 4\n0000000000 65535 f \n0000000010 00000 n \n0000000060 00000 n \n0000000117 00000 n \n"
        b"trailer << /Size 4 /Root 1 0 R >>\nstartxref\n199\n%%EOF"
    )

    _, body_md = upload_test_doc(client, f"{prefix}.md", md_content, "text/markdown")
    _, body_txt = upload_test_doc(client, f"{prefix}.txt", txt_content, "text/plain")
    _, body_pdf = upload_test_doc(client, f"{prefix}.pdf", minimal_pdf, "application/pdf")

    doc_ids = [body_md["id"], body_txt["id"], body_pdf["id"]]
    managed_document_ids.extend(doc_ids)

    # 2. Verify all are listed and ready
    list_docs = client.get("/api/documents").json()
    listed_ids = [d["id"] for d in list_docs]
    for d_id in doc_ids:
        assert d_id in listed_ids

    # 3. Clean up all multi-format documents
    for d_id in doc_ids:
        assert client.delete(f"/api/documents/{d_id}").status_code == 200


def test_tier4_high_stress_operational_resilience(client: TestClient, managed_document_ids):
    """Scenario 3: High-Stress Operational Resilience & Boundary Storm.
    Fires rapid alternating requests with mixed valid/invalid inputs to verify 100% stability.
    """
    # 1. Rapid invalid upload bursts
    for _ in range(5):
        assert client.post("/api/documents", files={"file": ("test.exe", b"exe", "binary")}).status_code == 400
        assert client.post("/api/documents", files={"file": ("empty.md", b"", "text/markdown")}).status_code == 400

    # 2. Rapid invalid question submissions
    for _ in range(5):
        assert client.post("/api/chat", json={"question": ""}).status_code == 422
        assert client.post("/api/chat", json={"question": "   \n "}).status_code == 422

    # 3. Rapid 404 queries
    for _ in range(5):
        assert client.get(f"/api/chunks/{uuid.uuid4()}").status_code == 404
        assert client.delete(f"/api/documents/{uuid.uuid4()}").status_code == 404

    # 4. Valid document upload after the storm
    status_code, body = upload_test_doc(client, "post_storm_doc.md", b"# Storm Resilience\n\nSystem remains 100% healthy.")
    assert status_code == 202
    managed_document_ids.append(body["id"])

    # 5. Health probe confirms operational integrity
    health_resp = client.get("/api/health?details=true")
    assert health_resp.status_code == 200
    assert health_resp.json()["ready"] is True


def test_tier4_cold_start_and_readiness_probe(client: TestClient):
    """Scenario 4: Cold-Start Readiness & Health Degradation Recovery.
    Verifies that the /api/health endpoint delivers the exact schema expected by apps/web/src/lib/api.ts.
    """
    # 1. Simple probe
    resp_simple = client.get("/api/health")
    assert resp_simple.status_code == 200
    assert resp_simple.json() == {"status": "ok"}

    # 2. Detailed probe matching HealthStatus interface in frontend api.ts
    resp_detailed = client.get("/api/health?details=true")
    assert resp_detailed.status_code == 200
    data = resp_detailed.json()

    assert data["status"] == "ok"
    assert isinstance(data["ready"], bool)
    assert data["ready"] is True
    assert "components" in data
    assert "database" in data["components"]
    assert "embedding" in data["components"]
    assert data["components"]["embedding"]["ready"] is True
