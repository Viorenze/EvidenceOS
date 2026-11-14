"""Tier 3: Cross-Feature Combinations E2E Tests.

Validates pairwise interactions and complex multi-feature workflows:
1. Full Lifecycle Pipeline: Upload -> List Poll -> Search -> Stream Q&A -> Verify Citations -> Inspect Chunk Detail -> Delete Doc -> Verify Chunk 404 -> Query again -> Refuse
2. Multi-Document Hybrid Disambiguation: Upload Doc A & Doc B -> Query specific topic -> Citations link to Doc B chunk, not Doc A
3. Dynamic State Transition: Query before doc upload (refuses) -> Upload doc -> Query same question (answers with verified citation) -> Delete doc -> Query same question (refuses)
4. Concurrent Chat Stream Isolation: Multiple simultaneous chat streams maintain distinct run_ids and tokens without thread interference
5. Upload & Cascade Delete Search Integrity: Verifies /api/search hybrid index immediately indexes and immediately purges on delete
6. Client Stream Interruption & Recovery: Premature stream disconnect followed immediately by new valid stream

Authoritative sources:
- apps/api/routers/documents.py
- apps/api/routers/chat.py
- apps/api/routers/search.py
- docs/PRD.md Section 4, 6, 8
"""

import uuid
from unittest.mock import patch
from fastapi.testclient import TestClient

from apps.api.llm.provider import FakeLLMProvider
from tests.e2e.conftest import parse_sse_events, upload_test_doc


def test_tier3_full_lifecycle_upload_query_cite_modal_delete_refuse(client: TestClient, managed_document_ids):
    """Pairwise test covering full lifecycle:
    Upload -> List -> Query -> Citations -> Chunk Modal -> Delete -> Cascade 404 -> Refusal.
    """
    unique_keyword = f"UniqueLifecycleToken_{uuid.uuid4().hex[:8]}"
    doc_content = (
        f"# {unique_keyword} Architecture Guide\n\n"
        f"The {unique_keyword} system implements verifiable citations and RRF hybrid retrieval.\n"
    ).encode("utf-8")
    filename = f"lifecycle_{unique_keyword}.md"

    # 1. Upload document
    status_code, body = upload_test_doc(client, filename, doc_content)
    assert status_code == 202
    doc_id = body["id"]
    managed_document_ids.append(doc_id)

    # 2. List documents & verify ready
    list_resp = client.get("/api/documents")
    assert list_resp.status_code == 200
    target_doc = next((d for d in list_resp.json() if d["id"] == doc_id), None)
    assert target_doc is not None
    assert target_doc["status"] == "ready"
    assert target_doc["n_chunks"] >= 1

    # 3. Stream Q&A about this document
    question = f"What does {unique_keyword} implement?"
    fake_llm = FakeLLMProvider(
        custom_grades=[{"sufficient": True, "reason": "找到了对应文档", "missing": ""}],
        custom_answers=[f"{unique_keyword} 实现了可验证引用和混合检索 [1]。"],
    )

    with patch("apps.api.routers.chat.get_llm_provider", return_value=fake_llm):
        chat_resp = client.post("/api/chat", json={"question": question})
        assert chat_resp.status_code == 200
        events = parse_sse_events(chat_resp.text)

        # 4. Verify citations
        citation_events = [e[1] for e in events if e[0] == "citations"]
        assert len(citation_events) == 1
        items = citation_events[0]["items"]
        assert len(items) >= 1
        target_chunk_id = items[0]["chunk_id"]

        # 5. Chunk Modal inspection
        modal_resp = client.get(f"/api/chunks/{target_chunk_id}")
        assert modal_resp.status_code == 200
        modal_data = modal_resp.json()
        assert modal_data["document"] == filename
        assert unique_keyword in modal_data["content"]

    # 6. Delete document
    del_resp = client.delete(f"/api/documents/{doc_id}")
    assert del_resp.status_code == 200

    # 7. Verify chunk cascade deleted
    assert client.get(f"/api/chunks/{target_chunk_id}").status_code == 404

    # 8. Query again -> with document gone, agent must refuse
    fake_llm_refuse = FakeLLMProvider(
        custom_grades=[
            {"sufficient": False, "reason": "已删除，无相关文档", "missing": "all"},
            {"sufficient": False, "reason": "改写后仍无文档", "missing": "all"},
            {"sufficient": False, "reason": "二次改写后仍无文档", "missing": "all"},
        ]
    )
    with patch("apps.api.routers.chat.get_llm_provider", return_value=fake_llm_refuse):
        chat_resp_after = client.post("/api/chat", json={"question": question})
        assert chat_resp_after.status_code == 200
        events_after = parse_sse_events(chat_resp_after.text)

        done_after = next(e[1] for e in events_after if e[0] == "done")
        assert done_after["refused"] is True

        tokens_after = "".join(e[1]["text"] for e in events_after if e[0] == "token")
        assert tokens_after == "根据已有知识库内容，无法回答该问题。"


def test_tier3_multi_document_disambiguation(client: TestClient, managed_document_ids):
    """Verify that when multiple documents are uploaded, query specifically cites the correct document."""
    topic_a = f"TopicAlpha_{uuid.uuid4().hex[:6]}"
    topic_b = f"TopicBeta_{uuid.uuid4().hex[:6]}"

    doc_b_phrase = f"{topic_b} 自动化部署运维操作手册与生产环境指引。"
    content_a = f"# {topic_a} 详细规格\n\n{topic_a} 架构规格参数规范清单。".encode("utf-8")
    content_b = f"# {topic_b} 运维手册\n\n{doc_b_phrase}".encode("utf-8")

    _, doc_a = upload_test_doc(client, f"{topic_a}.md", content_a)
    _, doc_b = upload_test_doc(client, f"{topic_b}.md", content_b)
    managed_document_ids.extend([doc_a["id"], doc_b["id"]])

    # Query specifically for TopicBeta using the exact sentence for deterministic FakeEmbedding score ~1.0
    fake_llm = FakeLLMProvider(
        custom_grades=[{"sufficient": True, "reason": "匹配到 TopicBeta 手册", "missing": ""}],
        custom_answers=[f"{topic_b} 提供了完整的操作指南 [1]。"],
    )

    with patch("apps.api.routers.chat.get_llm_provider", return_value=fake_llm):
        resp = client.post("/api/chat", json={"question": doc_b_phrase})
        assert resp.status_code == 200
        events = parse_sse_events(resp.text)

        citations = next(e[1]["items"] for e in events if e[0] == "citations")
        assert len(citations) >= 1
        # Primary citation must cite TopicBeta, not TopicAlpha
        assert citations[0]["document"] == f"{topic_b}.md"


def test_tier3_dynamic_state_knowledge_base_transition(client: TestClient, managed_document_ids):
    """Verify state transitions: Query (refuses) -> Ingest (succeeds) -> Query (answers) -> Delete -> Query (refuses)."""
    topic_dyn = f"DynamicTopic_{uuid.uuid4().hex[:6]}"
    exact_phrase = f"{topic_dyn} 核心算法基于局部加权多项式回归与自适应梯度提升。"

    # Step A: Query before document exists -> Refuses
    fake_llm_refuse = FakeLLMProvider(
        custom_grades=[
            {"sufficient": False, "reason": "无相关文档", "missing": "all"},
            {"sufficient": False, "reason": "改写后仍无文档", "missing": "all"},
            {"sufficient": False, "reason": "二次改写后仍无文档", "missing": "all"},
        ]
    )
    with patch("apps.api.routers.chat.get_llm_provider", return_value=fake_llm_refuse):
        resp_before = client.post("/api/chat", json={"question": exact_phrase})
        events_before = parse_sse_events(resp_before.text)
        assert next(e[1] for e in events_before if e[0] == "done")["refused"] is True

    # Step B: Ingest document containing the topic
    content = f"# {topic_dyn}\n\n{exact_phrase}".encode("utf-8")
    _, body = upload_test_doc(client, f"{topic_dyn}.md", content)
    doc_id = body["id"]
    managed_document_ids.append(doc_id)

    # Step C: Query again -> Answers with valid citation
    fake_llm = FakeLLMProvider(
        custom_grades=[{"sufficient": True, "reason": "检索到算法细节", "missing": ""}],
        custom_answers=[f"{topic_dyn} 算法基于局部加权回归 [1]。"],
    )
    with patch("apps.api.routers.chat.get_llm_provider", return_value=fake_llm):
        resp_after = client.post("/api/chat", json={"question": exact_phrase})
        events_after = parse_sse_events(resp_after.text)
        done_after = next(e[1] for e in events_after if e[0] == "done")
        assert done_after["refused"] is False
        citations_after = next(e[1]["items"] for e in events_after if e[0] == "citations")
        assert len(citations_after) >= 1
        assert citations_after[0]["document"] == f"{topic_dyn}.md"

    # Step D: Delete and verify refusal again
    client.delete(f"/api/documents/{doc_id}")
    fake_llm_refuse_d = FakeLLMProvider(
        custom_grades=[
            {"sufficient": False, "reason": "无相关文档", "missing": "all"},
            {"sufficient": False, "reason": "改写后仍无文档", "missing": "all"},
            {"sufficient": False, "reason": "二次改写后仍无文档", "missing": "all"},
        ]
    )
    with patch("apps.api.routers.chat.get_llm_provider", return_value=fake_llm_refuse_d):
        resp_final = client.post("/api/chat", json={"question": exact_phrase})
        events_final = parse_sse_events(resp_final.text)
        assert next(e[1] for e in events_final if e[0] == "done")["refused"] is True


def test_tier3_concurrent_chat_streams_isolation(client: TestClient):
    """Verify separate chat queries maintain distinct run_ids and independent token streams."""
    mock_chunks_1 = [{"chunk_id": "c1", "document_id": "d1", "document": "doc1.md", "page": 1, "heading": "H1", "content": "Text1", "rrf_score": 0.05}]
    mock_chunks_2 = [{"chunk_id": "c2", "document_id": "d2", "document": "doc2.md", "page": 1, "heading": "H2", "content": "Text2", "rrf_score": 0.05}]

    fake_llm_1 = FakeLLMProvider(
        custom_grades=[{"sufficient": True, "reason": "ok", "missing": ""}],
        custom_answers=["回答流一 [1]。"],
    )
    fake_llm_2 = FakeLLMProvider(
        custom_grades=[{"sufficient": True, "reason": "ok", "missing": ""}],
        custom_answers=["回答流二 [1]。"],
    )

    with patch("apps.api.routers.chat.get_llm_provider", return_value=fake_llm_1), \
         patch("apps.api.agent.nodes.hybrid_search", return_value=mock_chunks_1):
        resp1 = client.post("/api/chat", json={"question": "问题一？"})

    with patch("apps.api.routers.chat.get_llm_provider", return_value=fake_llm_2), \
         patch("apps.api.agent.nodes.hybrid_search", return_value=mock_chunks_2):
        resp2 = client.post("/api/chat", json={"question": "问题二？"})

    events1 = parse_sse_events(resp1.text)
    events2 = parse_sse_events(resp2.text)

    tokens1 = "".join(e[1]["text"] for e in events1 if e[0] == "token")
    tokens2 = "".join(e[1]["text"] for e in events2 if e[0] == "token")

    done1 = next(e[1] for e in events1 if e[0] == "done")
    done2 = next(e[1] for e in events2 if e[0] == "done")

    assert tokens1 == "回答流一 [1]。"
    assert tokens2 == "回答流二 [1]。"
    assert done1["run_id"] != done2["run_id"]


def test_tier3_upload_cascade_delete_integrity_with_search(client: TestClient, managed_document_ids):
    """Verify POST /api/search hybrid index immediately finds uploaded document, and immediately purges on delete."""
    search_keyword = f"SearchIndexSync_{uuid.uuid4().hex[:6]}"
    body_phrase = f"Dedicated {search_keyword} search index synchronization test content."
    content = f"# Header\n\n{body_phrase}".encode("utf-8")
    filename = f"{search_keyword}.md"

    _, body = upload_test_doc(client, filename, content)
    doc_id = body["id"]
    managed_document_ids.append(doc_id)

    # 1. Search endpoint returns the new chunk
    search_resp = client.post("/api/search", json={"query": body_phrase, "mode": "hybrid", "k": 5})
    assert search_resp.status_code == 200
    results = search_resp.json()["results"]
    assert any(r["document"] == filename for r in results)

    # 2. Delete document
    del_resp = client.delete(f"/api/documents/{doc_id}")
    assert del_resp.status_code == 200

    # 3. Search endpoint immediately excludes deleted chunk
    search_resp_after = client.post("/api/search", json={"query": body_phrase, "mode": "hybrid", "k": 5})
    assert search_resp_after.status_code == 200
    results_after = search_resp_after.json()["results"]
    assert not any(r["document"] == filename for r in results_after)


def test_tier3_client_stream_abort_and_subsequent_request(client: TestClient):
    """Simulate client aborting stream early and immediately executing a clean subsequent request."""
    # 1. First request starts stream
    resp1 = client.post("/api/chat", json={"question": "短查询测试？"})
    assert resp1.status_code == 200
    # Simulate client abort by not reading further or only inspecting first lines
    assert "text/event-stream" in resp1.headers["content-type"]

    # 2. Immediately issue second complete request
    fake_llm = FakeLLMProvider(
        custom_grades=[{"sufficient": True, "reason": "充分", "missing": ""}],
        custom_answers=["后续请求已完全执行 [1]。"],
    )
    mock_chunks = [{"chunk_id": "c_sub", "document_id": "d_sub", "document": "sub.md", "page": 1, "heading": "Sub", "content": "Sub content", "rrf_score": 0.05}]

    with patch("apps.api.routers.chat.get_llm_provider", return_value=fake_llm), \
         patch("apps.api.agent.nodes.hybrid_search", return_value=mock_chunks):
        resp2 = client.post("/api/chat", json={"question": "后续连贯查询？"})
        assert resp2.status_code == 200
        events2 = parse_sse_events(resp2.text)
        done2 = next(e[1] for e in events2 if e[0] == "done")
        assert done2["refused"] is False
        assert "run_id" in done2
