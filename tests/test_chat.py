"""Unit and smoke tests for SSE chat streaming endpoint (/api/chat)."""

import json
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from apps.api.config import Settings
from apps.api.llm.provider import FakeLLMProvider
from apps.api.main import app

MOCK_CHUNKS = [
    {
        "chunk_id": "chunk-sse-1",
        "document_id": "doc-sse-1",
        "document": "fastapi_guide.md",
        "page": 1,
        "heading": "Dependency Injection",
        "content": "FastAPI 原生支持依赖注入系统，通过 Depends 声明。",
        "rrf_score": 0.033,
    }
]


def parse_sse_events(raw_text: str):
    """Parse raw SSE stream text into a list of (event_type, json_data) tuples."""
    events = []
    lines = raw_text.strip().split("\n")
    current_event = None
    for line in lines:
        if line.startswith("event: "):
            current_event = line[7:].strip()
        elif line.startswith("data: ") and current_event:
            data_str = line[6:].strip()
            data_obj = json.loads(data_str)
            events.append((current_event, data_obj))
            current_event = None
    return events


def test_chat_empty_question(client: TestClient):
    """Verify empty question returns HTTP 422."""
    resp = client.post("/api/chat", json={"question": "   "})
    assert resp.status_code == 422


@patch("apps.api.agent.nodes.hybrid_search", return_value=MOCK_CHUNKS)
def test_chat_sse_stream_answerable(mock_search, client: TestClient):
    """Verify SSE streaming for an answerable question emits steps, tokens, citations, and done."""
    fake_llm = FakeLLMProvider(
        custom_grades=[{"sufficient": True, "reason": "检索到的内容充分", "missing": ""}],
        custom_answers=["FastAPI 原生支持依赖注入 [1]。"],
    )

    with patch("apps.api.routers.chat.get_llm_provider", return_value=fake_llm):
        resp = client.post("/api/chat", json={"question": "FastAPI 如何做依赖注入？"})
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

        events = parse_sse_events(resp.text)
        event_types = [e[0] for e in events]

        # 1. Verify all event types exist in correct sequence
        assert "step" in event_types
        assert "token" in event_types
        assert "citations" in event_types
        assert "done" in event_types
        assert "error" not in event_types

        # 2. Verify step progression
        steps = [e[1] for e in events if e[0] == "step"]
        nodes = [s["node"] for s in steps]
        assert "retrieve" in nodes
        assert "grade" in nodes
        assert "generate" in nodes
        assert "verify_citations" in nodes

        # 3. Verify streamed tokens reconstruct the verified answer
        tokens = [e[1]["text"] for e in events if e[0] == "token"]
        reconstructed = "".join(tokens)
        assert reconstructed == "FastAPI 原生支持依赖注入 [1]。"

        # 4. Verify citations
        citation_events = [e[1] for e in events if e[0] == "citations"]
        assert len(citation_events) == 1
        items = citation_events[0]["items"]
        assert len(items) == 1
        assert items[0]["n"] == 1
        assert items[0]["chunk_id"] == "chunk-sse-1"

        # 5. Verify done metadata
        done_events = [e[1] for e in events if e[0] == "done"]
        assert len(done_events) == 1
        assert done_events[0]["refused"] is False
        assert done_events[0]["latency_ms"] > 0
        assert done_events[0]["run_id"]


@patch("apps.api.agent.nodes.hybrid_search", return_value=MOCK_CHUNKS)
def test_chat_sse_stream_refusal(mock_search, client: TestClient):
    """Verify SSE streaming for unanswerable question emits refusal step, fixed refusal token, and refused=True in done."""
    fake_llm = FakeLLMProvider(
        custom_grades=[
            {"sufficient": False, "reason": "未找到相关技术方案", "missing": "量子计算支持"},
            {"sufficient": False, "reason": "仍未找到相关方案", "missing": "量子计算支持"},
            {"sufficient": False, "reason": "三次检索均无证据", "missing": "量子计算支持"},
        ],
        custom_answers=["改写1", "改写2"],
    )

    with patch("apps.api.routers.chat.get_llm_provider", return_value=fake_llm):
        resp = client.post("/api/chat", json={"question": "FastAPI 如何接入超导量子计算机？"})
        assert resp.status_code == 200

        events = parse_sse_events(resp.text)
        steps = [e[1] for e in events if e[0] == "step"]
        nodes = [s["node"] for s in steps]
        assert "refuse" in nodes

        tokens = [e[1]["text"] for e in events if e[0] == "token"]
        assert "".join(tokens) == "根据已有知识库内容，无法回答该问题。"

        citation_events = [e[1] for e in events if e[0] == "citations"]
        assert citation_events[0]["items"] == []

        done_events = [e[1] for e in events if e[0] == "done"]
        assert done_events[0]["refused"] is True


def test_chat_sse_stream_error_handling(client: TestClient):
    """Verify unexpected internal exception during stream emits error event and no done event."""
    with patch("apps.api.routers.chat.create_agent", side_effect=RuntimeError("Graph compilation failed")):
        resp = client.post("/api/chat", json={"question": "测试异常处理"})
        assert resp.status_code == 200

        events = parse_sse_events(resp.text)
        event_types = [e[0] for e in events]
        assert "error" in event_types
        assert "done" not in event_types

        error_event = [e[1] for e in events if e[0] == "error"][0]
        assert "Graph compilation failed" in error_event["message"]
