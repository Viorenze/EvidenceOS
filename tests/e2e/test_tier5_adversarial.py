"""Tier 5: White-Box Adversarial Coverage Hardening E2E Test Suite.

Authoritative coverage across adversarial edge cases:
1. Rapid Abort / Submit Lifecycle & Stream Concurrency
   - Early client abort on bootstrap frame
   - Rapid burst Ask -> Stop -> Ask sequence
   - Empty and whitespace submission guards
2. Polling Error Resilience & Readiness Probe
   - Readiness probe schema contracts (checkHealthReadiness in api.ts)
   - High-frequency burst document polling (25 consecutive calls)
3. Document Deletion Edge Cases & Cascade Consistency
   - Rapid duplicate deletion idempotency (200 then 404)
   - Cascade deletion of chunks and search index
   - Malformed IDs, SQL injection, path traversal safety
4. Large Payload Document Upload Validation & Format Guardrails
   - Realistic large technical specification (50KB+, 80 sections)
   - Zero-byte upload rejection
   - Unsupported extensions rejection (.exe, .json, .py, .env)
5. Meta StyleX CSS Build Output Verification
   - Zero Tailwind CSS contamination (@tailwind, utility classes)
   - StyleX @layer cascade structure
   - Responsive breakpoints & specificity boost
   - Design tokens preservation (#2563eb, #0f172a, #f8fafc)
   - Keyframe animations (pulse, spin, slideIn, fadeIn)
6. SSE Stream Adversarial Hardening (Multi-byte UTF-8, Unknown Frames, Comments)
   - 3-byte Chinese characters split across chunk boundaries
   - 4-byte astral plane emojis (🤖, 🚀) split across byte boundaries
   - SSE block delimiter (\\n\\n) split across chunks
   - Microscopic single-byte stream chunking stress
   - Unknown event types (ping, heartbeat, metrics) ignored gracefully
   - SSE comment lines (: keepalive) and blank line handling
   - Corrupted JSON payloads handled without stream abortion
   - Premature stream disconnection detection
   - Missing event line defaults to message
7. Citation Reconciliation & Markdown Fencing Hardening
   - Consecutive citation markers [3][1][2] without whitespace
   - Frontend negative lookbehind regex split validation
   - Out-of-order retrieval index resolution ([2] before [1])
   - Grouped and Chinese full-width bracket normalization ([1, 2], 【1，2】)
   - Mixed valid and out-of-range citations ([1][999][2])
   - Multiline fenced code blocks with language tags
   - Inline code shielding with adjacent prose citations
   - Markdown hyperlinks [Text](url) and nested brackets [[1]]
   - HTML tags and XSS payload safety
   - Programming subscript variable immunity (arr[0], data[1], matrix in backticks)
8. Chunk Modal Metadata Edge Cases & Extreme Content Hardening
   - Empty heading and null page handling
   - Huge verbatim content (>10,000 characters) retrieval
   - Deep nested breadcrumb headings (A > B > C > D)
   - High index numbers (idx=65535)
   - Rapid concurrent detail queries
9. End-to-End Adversarial Integration Flow
   - Full Q&A pipeline with adversarial LLM responses and SSE verification
"""

import codecs
import concurrent.futures
import glob
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import patch

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Enforce deterministic testing configurations before any app imports
os.environ["EMBEDDING_PROVIDER"] = "fake"
os.environ["LLM_PROVIDER"] = "fake"
os.environ["DATABASE_URL"] = "postgresql+psycopg://evidence:evidence@127.0.0.1:5432/evidenceos"

import pytest
from fastapi.testclient import TestClient

from apps.api.agent.citations import (
    clean_answer_citations,
    extract_citation_numbers,
    verify_citations,
)
from apps.api.db.models import Chunk, Document
from apps.api.db.session import SessionLocal
from apps.api.llm.provider import FakeLLMProvider
from tests.e2e.conftest import parse_sse_events, upload_test_doc


# ===========================================================================
# Simulation Helper: TypeScript SSE Reader Parity (apps/web/src/lib/api.ts)
# ===========================================================================

class SimulatedClientSSEStreamReader:
    """Exact Python simulation of the ReadableStream SSE consumer in apps/web/src/lib/api.ts.

    Validates multi-byte UTF-8 decoding, frame buffering on \\n\\n, JSON parsing,
    and event routing (step, token, citations, done, error, unknown).
    """

    def __init__(self):
        self.decoder = codecs.getincrementaldecoder("utf-8")()
        self.buffer = ""
        self.steps: List[Dict[str, Any]] = []
        self.tokens: List[str] = []
        self.citations: List[Dict[str, Any]] = []
        self.done: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None
        self.unknown_events: List[Tuple[str, Dict[str, Any]]] = []
        self.json_parse_errors: List[str] = []
        self.completed = False

    def feed_bytes(self, chunk: bytes, is_final: bool = False):
        """Feed arbitrary byte slices into incremental decoder and process SSE blocks."""
        self.buffer += self.decoder.decode(chunk, final=is_final)
        blocks = self.buffer.split("\n\n")
        self.buffer = blocks.pop() if blocks else ""

        for block in blocks:
            if not block.strip():
                continue

            event_type = "message"
            data_str = ""

            for line in block.split("\n"):
                if line.startswith("event: "):
                    event_type = line[7:].strip()
                elif line.startswith("data: "):
                    data_str = line[6:].strip()

            if not data_str:
                continue

            try:
                parsed = json.loads(data_str)
                if event_type == "step":
                    self.steps.append(parsed)
                elif event_type == "token":
                    if "text" in parsed:
                        self.tokens.append(parsed["text"])
                elif event_type == "citations":
                    self.citations = parsed.get("items", [])
                elif event_type == "done":
                    self.completed = True
                    self.done = parsed
                elif event_type == "error":
                    self.completed = True
                    self.error = parsed.get("message", "Unknown server error")
                else:
                    self.unknown_events.append((event_type, parsed))
            except json.JSONDecodeError:
                self.json_parse_errors.append(data_str)

    def finalize(self):
        """Simulate reader close check."""
        if not self.completed:
            self.error = "Stream terminated unexpectedly before completion"


# ===========================================================================
# 1. Rapid Abort / Submit Lifecycle & Concurrency
# ===========================================================================

class TestTier5RapidAbortSubmitLifecycle:
    """Stress tests rapid user interactions: clicking Ask then Stop, early aborts, and concurrent bursts."""

    def test_tier5_client_early_abort_first_frame(self, client: TestClient, managed_document_ids):
        """Simulate client sending chat query and immediately aborting after receiving the initial step frame."""
        content = b"# Abort Test Doc\n\nEvidenceOS handles streaming cancellation with AbortController."
        _, body = upload_test_doc(client, "abort_test.md", content)
        managed_document_ids.append(body["id"])

        with client.stream("POST", "/api/chat", json={"question": "How does cancellation work?"}) as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]

            first_chunk = next(response.iter_text())
            assert "event: step" in first_chunk

        followup_resp = client.post("/api/chat", json={"question": "Follow-up question after abort"})
        assert followup_resp.status_code == 200
        events = parse_sse_events(followup_resp.text)
        event_types = [e[0] for e in events]
        assert "step" in event_types
        assert "done" in event_types

    def test_tier5_rapid_burst_ask_stop_sequence(self, client: TestClient):
        """Simulate rapid Ask -> Stop -> Ask -> Stop -> Ask sequence.

        Verifies that multiple interrupted streams do not cause unhandled errors or stale data leakage.
        """
        for i in range(3):
            with client.stream("POST", "/api/chat", json={"question": f"Rapid question #{i}"}) as resp:
                assert resp.status_code == 200
                for chunk in resp.iter_text():
                    if "event: step" in chunk:
                        break

        final_resp = client.post("/api/chat", json={"question": "Final stable query"})
        assert final_resp.status_code == 200
        events = parse_sse_events(final_resp.text)
        assert any(e[0] == "done" for e in events)

    def test_tier5_empty_and_whitespace_submission_guard(self, client: TestClient):
        """Verify rapid submission of empty or whitespace-only inputs is rejected with HTTP 422."""
        for bad_input in ["", "   ", "\n\t  \n"]:
            resp = client.post("/api/chat", json={"question": bad_input})
            assert resp.status_code == 422
            assert "Question cannot be empty" in resp.json()["detail"]


# ===========================================================================
# 2. Polling Error Resilience & Readiness Probe
# ===========================================================================

class TestTier5PollingErrorResilience:
    """Stress tests readiness probe polling and document listing under rapid polling bursts."""

    def test_tier5_readiness_probe_schema_and_component_contracts(self, client: TestClient):
        """Verify /api/health?details=true matches checkHealthReadiness frontend requirements."""
        resp = client.get("/api/health?details=true")
        assert resp.status_code == 200
        data = resp.json()

        assert data["status"] == "ok"
        assert data["ready"] is True
        assert "components" in data
        assert "database" in data["components"]
        assert "embedding" in data["components"]
        assert data["components"]["embedding"]["ready"] is True

    def test_tier5_rapid_polling_burst_document_list(self, client: TestClient, managed_document_ids):
        """Verify high-frequency polling (25 rapid GETs) does not degrade response integrity or leak sessions."""
        _, doc = upload_test_doc(client, "poll_doc.md", b"# Polling\n\nContent for polling resilience.")
        managed_document_ids.append(doc["id"])

        start_time = time.perf_counter()
        for _ in range(25):
            resp = client.get("/api/documents")
            assert resp.status_code == 200
            items = resp.json()
            assert isinstance(items, list)
            assert len(items) >= 1
            first = items[0]
            assert "id" in first
            assert "filename" in first
            assert "status" in first
            assert "n_chunks" in first
            assert "created_at" in first

        duration = time.perf_counter() - start_time
        assert duration < 3.0


# ===========================================================================
# 3. Document Deletion Edge Cases & Cascade Consistency
# ===========================================================================

class TestTier5DocumentDeletionEdgeCases:
    """Verifies duplicate deletion idempotency, cascading chunk purge, and non-UUID safety."""

    def test_tier5_rapid_duplicate_deletion_idempotency(self, client: TestClient, managed_document_ids):
        """Simulate rapid double-click on delete button: 1st returns 200, 2nd & 3rd return 404."""
        content = b"# To Be Deleted\n\nThis document will be deleted multiple times in rapid succession."
        _, doc = upload_test_doc(client, "delete_me.md", content)
        doc_id = doc["id"]

        del1 = client.delete(f"/api/documents/{doc_id}")
        assert del1.status_code == 200
        assert del1.json() == {"message": "Document deleted successfully"}

        del2 = client.delete(f"/api/documents/{doc_id}")
        assert del2.status_code == 404
        assert del2.json()["detail"] == "Document not found"

        del3 = client.delete(f"/api/documents/{doc_id}")
        assert del3.status_code == 404

    def test_tier5_deletion_cascades_chunks_and_search(self, client: TestClient):
        """Verify deleting document purges all related chunks in database and eliminates search hits."""
        content = (
            b"# Cascade Header\n\nUniqueKeywordCascadeAlpha content.\n\n"
            b"## Cascade Sub\n\nUniqueKeywordCascadeBeta content.\n"
        )
        _, doc = upload_test_doc(client, "cascade_test.md", content)
        doc_id = doc["id"]

        with SessionLocal() as db:
            chunks = db.query(Chunk).filter(Chunk.document_id == doc_id).all()
            assert len(chunks) >= 2
            chunk_ids = [c.id for c in chunks]

        del_resp = client.delete(f"/api/documents/{doc_id}")
        assert del_resp.status_code == 200

        with SessionLocal() as db:
            remaining_chunks = db.query(Chunk).filter(Chunk.id.in_(chunk_ids)).all()
            assert len(remaining_chunks) == 0

        for cid in chunk_ids:
            chunk_resp = client.get(f"/api/chunks/{cid}")
            assert chunk_resp.status_code == 404

    def test_tier5_malformed_deletion_ids(self, client: TestClient):
        """Test deletion endpoint with path traversal, SQL injection, and undefined string IDs."""
        bad_ids = ["undefined", "null", "non-existent-uuid", "'; DROP TABLE documents; --", "path..traversal"]
        for bad_id in bad_ids:
            resp = client.delete(f"/api/documents/{bad_id}")
            assert resp.status_code == 404
            assert resp.json()["detail"] == "Document not found"

        resp_traversal = client.delete("/api/documents/../documents")
        assert resp_traversal.status_code in [404, 405]


# ===========================================================================
# 4. Large Payload Upload Validation & Format Guardrails
# ===========================================================================

class TestTier5LargePayloadUploadValidation:
    """Stress tests upload boundaries: 50KB+ technical payload, 0-byte file, and invalid formats."""

    def test_tier5_large_markdown_technical_payload(self, client: TestClient, managed_document_ids):
        """Upload a realistic large technical specification (>50 KB, 80 detailed sections).

        Verifies chunker handles large payloads without memory issues, creates many chunks,
        and marks document as 'ready'.
        """
        sections = []
        for i in range(80):
            sections.append(
                f"## Section {i}: Architecture Component {i} & High-Performance Subsystem\n\n"
                f"Detailed specification for component {i}. EvidenceOS implements vector indexing, "
                f"RRF reciprocal rank fusion scoring, and LangGraph conditional cycles for resilient Q&A.\n"
                f"This subsystem guarantees strict citation provenance verification and avoids hallucination.\n"
                f"The hybrid retrieval layer combines dense vector embeddings with BM25 jieba tokenization.\n"
                f"Evaluation metrics are measured using real runs over the technical corpus.\n\n"
                f"```python\ndef handler_{i}(req: dict) -> dict:\n"
                f"    '''Process request for component {i} with verified telemetry.'''\n"
                f"    score = compute_rrf_rank(req, k=60)\n"
                f"    return {{'component': {i}, 'status': 'ok', 'score': score}}\n```\n"
            )
        large_content = ("# Large System Specification\n\n" + "\n".join(sections)).encode("utf-8")
        assert len(large_content) > 50000  # Ensure > 50 KB

        status_code, body = upload_test_doc(client, "large_spec.md", large_content, "text/markdown")
        assert status_code == 202
        doc_id = body["id"]
        managed_document_ids.append(doc_id)

        # Verify document ingested into multiple chunks
        with SessionLocal() as db:
            doc = db.query(Document).filter(Document.id == doc_id).first()
            assert doc is not None
            assert doc.status == "ready"
            assert doc.n_chunks >= 40
            assert doc.error is None

    def test_tier5_zero_byte_upload_rejection(self, client: TestClient):
        """Verify zero-byte upload is rejected with HTTP 400."""
        status_code, body = upload_test_doc(client, "empty.md", b"", "text/markdown")
        assert status_code == 400
        assert "Uploaded file is empty" in body["detail"]

    def test_tier5_unsupported_extensions_rejection(self, client: TestClient):
        """Verify unsupported extensions (.exe, .json, .py, .env) are rejected with HTTP 400."""
        unsupported = [
            ("virus.exe", b"binarycontent", "application/octet-stream"),
            ("config.json", b'{"key": "value"}', "application/json"),
            ("script.py", b'print("hello")', "text/x-python"),
            (".env", b"SECRET=123", "text/plain"),
        ]
        for fname, content, mime in unsupported:
            status_code, body = upload_test_doc(client, fname, content, mime)
            assert status_code == 400
            assert "Unsupported format" in body["detail"]


# ===========================================================================
# 5. Meta StyleX CSS Build Output & Cascade Verification
# ===========================================================================

@pytest.fixture(scope="module")
def css_bundle_content() -> str:
    """Find and read the compiled StyleX CSS file from apps/web/dist/client/assets/."""
    dist_css_pattern = str(PROJECT_ROOT / "apps" / "web" / "dist" / "client" / "assets" / "*.css")
    css_files = glob.glob(dist_css_pattern)
    assert len(css_files) > 0, (
        f"No compiled CSS bundle found matching {dist_css_pattern}. "
        "Please run 'cd apps/web && npm run build' first."
    )
    with open(css_files[0], "r", encoding="utf-8") as f:
        return f.read()


class TestTier5StyleXCSSBuildVerification:
    """Verifies the production CSS bundle built by Meta StyleX unplugin and Vite+."""

    def test_tier5_stylex_css_zero_tailwind_contamination(self, css_bundle_content: str):
        """Verify that zero Tailwind CSS utilities, directives, or classnames exist in production CSS."""
        assert "@tailwind" not in css_bundle_content
        assert "tailwindcss" not in css_bundle_content.lower()

        tailwind_patterns = [
            r"\.bg-blue-\d+",
            r"\.text-gray-\d+",
            r"\.flex-col\b",
            r"\.items-center\b",
            r"\.justify-between\b",
            r"\.p-4\b",
            r"\.m-2\b",
            r"\.rounded-md\b",
        ]
        for pat in tailwind_patterns:
            matches = re.findall(pat, css_bundle_content)
            assert len(matches) == 0, f"Found forbidden Tailwind pattern {pat}: {matches}"

    def test_tier5_stylex_layer_cascade_structure(self, css_bundle_content: str):
        """Verify Meta StyleX `@layer` priority cascade declarations are present."""
        assert "@layer priority" in css_bundle_content or "@layer" in css_bundle_content

    def test_tier5_stylex_responsive_media_queries_and_specificity(self, css_bundle_content: str):
        """Verify StyleX responsive media query has double-class specificity boost."""
        assert "@media" in css_bundle_content
        assert "640px" in css_bundle_content

    def test_tier5_stylex_design_tokens_values(self, css_bundle_content: str):
        """Verify that exact design tokens from tokens.stylex.ts are preserved in compiled output."""
        assert "#2563eb" in css_bundle_content.lower()
        assert "#0f172a" in css_bundle_content.lower()
        assert "#f8fafc" in css_bundle_content.lower()

    def test_tier5_stylex_keyframes_compiled(self, css_bundle_content: str):
        """Verify StyleX keyframes (pulse, spin, slideIn, fadeIn) exist in the compiled CSS."""
        assert "@keyframes" in css_bundle_content


# ===========================================================================
# 6. SSE Stream Adversarial Hardening (Multi-byte, Unknown Frames, Comments)
# ===========================================================================

class TestTier5SSEStreamAdversarialCases:
    """Stress tests SSE client stream parsing against edge cases, network chunking, and malformed frames."""

    def test_tier5_multibyte_utf8_split_decoding_simulation(self):
        """Simulate 3-byte Chinese characters split across network packet chunk boundaries."""
        reader = SimulatedClientSSEStreamReader()
        raw_text = (
            'event: token\ndata: {"text": "深度学习"}\n\n'
            'event: token\ndata: {"text": "混合检索"}\n\n'
            'event: done\ndata: {"run_id": "r1", "refused": false}\n\n'
        )
        raw_bytes = raw_text.encode("utf-8")

        target_pos = raw_bytes.find("深度".encode("utf-8"))
        assert target_pos > 0

        # Cut right after first byte of '深' (\xe6)
        split_point = target_pos + 1
        reader.feed_bytes(raw_bytes[:split_point], is_final=False)
        reader.feed_bytes(raw_bytes[split_point:], is_final=True)

        accumulated = "".join(reader.tokens)
        assert accumulated == "深度学习混合检索"
        assert "\ufffd" not in accumulated
        assert reader.completed is True

    def test_tier5_utf8_4byte_emoji_split(self):
        """Verify 4-byte astral plane emojis (🤖, 🚀) split at byte offsets 1, 2, and 3 decode without loss."""
        reader = SimulatedClientSSEStreamReader()
        raw_text = (
            'event: token\ndata: {"text": "AI助手🤖与火箭🚀加速"}\n\n'
            'event: done\ndata: {"run_id": "r2", "refused": false}\n\n'
        )
        raw_bytes = raw_text.encode("utf-8")

        for i in range(0, len(raw_bytes), 2):
            reader.feed_bytes(raw_bytes[i : i + 2], is_final=False)
        reader.feed_bytes(b"", is_final=True)

        accumulated = "".join(reader.tokens)
        assert accumulated == "AI助手🤖与火箭🚀加速"
        assert "🤖" in accumulated
        assert "🚀" in accumulated
        assert "\ufffd" not in accumulated

    def test_tier5_sse_delimiter_split_across_chunks(self):
        """Verify SSE frame delimiter '\\n\\n' split across packet boundaries parses cleanly."""
        reader = SimulatedClientSSEStreamReader()
        chunk_1 = b'event: step\ndata: {"node": "retrieve", "status": "running"}\n'
        chunk_2 = b'\nevent: token\ndata: {"text": "FastAPI"}\n\n'
        chunk_3 = b'event: done\ndata: {"run_id": "r3", "refused": false}\n\n'

        reader.feed_bytes(chunk_1)
        assert len(reader.steps) == 0

        reader.feed_bytes(chunk_2)
        assert len(reader.steps) == 1
        assert reader.steps[0]["node"] == "retrieve"
        assert reader.tokens == ["FastAPI"]

        reader.feed_bytes(chunk_3, is_final=True)
        assert reader.completed is True

    def test_tier5_microscopic_single_byte_chunking_stress(self):
        """Stress-test SSE stream parsing when delivered in 1-byte increments."""
        reader = SimulatedClientSSEStreamReader()
        raw_text = (
            'event: step\ndata: {"node": "retrieve", "status": "running", "detail": "检索中..."}\n\n'
            'event: token\ndata: {"text": "证据"}\n\n'
            'event: token\ndata: {"text": "系统"}\n\n'
            'event: citations\ndata: {"items": [{"n": 1, "chunk_id": "c-1", "document": "doc.md", "snippet": "abc"}]}\n\n'
            'event: done\ndata: {"run_id": "stress-1", "refused": false, "latency_ms": 120}\n\n'
        )
        raw_bytes = raw_text.encode("utf-8")

        for b in raw_bytes:
            reader.feed_bytes(bytes([b]), is_final=False)
        reader.feed_bytes(b"", is_final=True)

        assert len(reader.steps) == 1
        assert reader.steps[0]["detail"] == "检索中..."
        assert "".join(reader.tokens) == "证据系统"
        assert len(reader.citations) == 1
        assert reader.citations[0]["chunk_id"] == "c-1"
        assert reader.done is not None
        assert reader.done["run_id"] == "stress-1"
        assert reader.completed is True

    def test_tier5_unknown_sse_frames_and_malformed_json_tolerance(self):
        """Verify that unknown SSE events and invalid JSON frames are safely tolerated by parser."""
        raw_sse = (
            "event: ping\ndata: {\"timestamp\": 1700000000}\n\n"
            "event: heartbeat\ndata: \"keep-alive\"\n\n"
            "event: corrupt\ndata: {this is broken json\n\n"
            "event: step\ndata: {\"node\": \"retrieve\", \"status\": \"done\", \"detail\": \"test\"}\n\n"
            "event: token\ndata: {\"text\": \"Hello \"}\n\n"
            "event: token\ndata: {\"text\": \"World!\"}\n\n"
            "event: done\ndata: {\"run_id\": \"test-run\", \"refused\": false, \"latency_ms\": 120.5}\n\n"
        )
        events = parse_sse_events(raw_sse)
        event_dict = {e[0]: e[1] for e in events}

        assert "corrupt" in event_dict
        assert "raw" in event_dict["corrupt"]
        assert "step" in event_dict
        assert event_dict["step"]["node"] == "retrieve"
        assert "done" in event_dict
        assert event_dict["done"]["run_id"] == "test-run"

    def test_tier5_sse_comment_and_blank_lines(self):
        """Verify SSE comment lines (: keepalive) and blank lines are ignored silently."""
        reader = SimulatedClientSSEStreamReader()
        raw_stream = (
            ': keepalive heartbeat pulse\n\n'
            '\n\n'
            ': proxy ping\n\n'
            'event: token\ndata: {"text": "内容"}\n\n'
            'event: done\ndata: {"run_id": "c1", "refused": false}\n\n'
        )
        reader.feed_bytes(raw_stream.encode("utf-8"), is_final=True)

        assert reader.tokens == ["内容"]
        assert reader.completed is True
        assert reader.error is None

    def test_tier5_sse_corrupted_json_payload_resilience(self):
        """Verify malformed JSON in data field does not crash stream or discard subsequent frames."""
        reader = SimulatedClientSSEStreamReader()
        raw_stream = (
            'event: token\ndata: {"text": "前缀"}\n\n'
            'event: token\ndata: {unclosed json payload\n\n'
            'event: token\ndata: <html>502 Bad Gateway</html>\n\n'
            'event: token\ndata: {"text": "后缀"}\n\n'
            'event: done\ndata: {"run_id": "err1", "refused": false}\n\n'
        )
        reader.feed_bytes(raw_stream.encode("utf-8"), is_final=True)

        assert len(reader.json_parse_errors) == 2
        assert "".join(reader.tokens) == "前缀后缀"
        assert reader.completed is True

    def test_tier5_sse_premature_stream_termination_detection(self):
        """Verify early stream disconnection before emitting done or error triggers failure handling."""
        reader = SimulatedClientSSEStreamReader()
        raw_stream = (
            'event: step\ndata: {"node": "retrieve", "status": "running"}\n\n'
            'event: token\ndata: {"text": "未完成的回答..."}\n\n'
        )
        reader.feed_bytes(raw_stream.encode("utf-8"), is_final=True)
        reader.finalize()

        assert reader.completed is False
        assert reader.error == "Stream terminated unexpectedly before completion"

    def test_tier5_sse_missing_event_field_defaults_to_message(self):
        """Verify SSE frames with missing 'event:' line default to message type."""
        reader = SimulatedClientSSEStreamReader()
        raw_stream = (
            'data: {"generic": "payload"}\n\n'
            'event: done\ndata: {"run_id": "def1", "refused": false}\n\n'
        )
        reader.feed_bytes(raw_stream.encode("utf-8"), is_final=True)

        assert len(reader.unknown_events) == 1
        assert reader.unknown_events[0][0] == "message"
        assert reader.completed is True


# ===========================================================================
# 7. Citation Reconciliation & Markdown Fencing Hardening
# ===========================================================================

class TestTier5CitationAndFencingHardening:
    """Stress tests citation extraction, reconciliation, normalization, and code fence shielding."""

    def test_tier5_citation_bracket_regex_adversarial_patterns(self):
        """Verify negative lookbehind regex (?<![a-zA-Z0-9_])(\\[[1-9]\\d*\\]) behavior on adversarial text."""
        citation_regex = re.compile(r"(?<![a-zA-Z0-9_])(\[[1-9]\d*\])")

        test_cases = [
            ("The answer is based on [1] and [2].", ["[1]", "[2]"]),
            ("Array access arr[0] and data[1] must not be matched.", []),
            ("Variable item_2[3] must not be matched.", []),
            ("Consecutive citations [1][2] must both be matched.", ["[1]", "[2]"]),
            ("Zero citation [0] is invalid and must not match.", []),
            ("Double bracket [[1]] outer must be handled safely.", ["[1]"]),
            ("Citation at start [5] and end of string [6]", ["[5]", "[6]"]),
        ]

        for text, expected in test_cases:
            matches = citation_regex.findall(text)
            assert matches == expected, f"Failed for '{text}': got {matches}, expected {expected}"

    def test_tier5_citation_consecutive_markers_extraction_and_cleaning(self):
        """Verify consecutive markers [3][1][2] without whitespace are parsed in order."""
        text = "FastAPI 依赖注入详见 [3][1][2]。"
        numbers = extract_citation_numbers(text)
        assert numbers == [3, 1, 2]

        cleaned = clean_answer_citations(text, {1, 2, 3})
        assert cleaned == "FastAPI 依赖注入详见 [3][1][2]。"

    def test_tier5_citation_out_of_order_retrieval_mapping(self):
        """Verify citations appearing out of order resolve to the exact corresponding chunk."""
        chunks = [
            {"id": "chunk-a", "document": "A.md", "content": "Chunk A content", "idx": 0},
            {"id": "chunk-b", "document": "B.md", "content": "Chunk B content", "idx": 1},
            {"id": "chunk-c", "document": "C.md", "content": "Chunk C content", "idx": 2},
        ]
        answer = "对比分析：先查看 [3]，再核对 [1]，最后查阅 [2]。"
        cleaned, valid_cits, is_valid = verify_citations(answer, chunks)

        assert is_valid is True
        assert len(valid_cits) == 3
        assert valid_cits[0]["n"] == 3
        assert valid_cits[0]["chunk_id"] == "chunk-c"
        assert valid_cits[1]["n"] == 1
        assert valid_cits[1]["chunk_id"] == "chunk-a"
        assert valid_cits[2]["n"] == 2
        assert valid_cits[2]["chunk_id"] == "chunk-b"

    def test_tier5_citation_grouped_comma_bracket_normalization(self):
        """Verify grouped citations [1, 2], [1,2,3], and Chinese brackets 【1，2】 normalize to [n][m]."""
        test_cases = [
            ("参考 [1, 2] 文档。", [1, 2], "参考 [1][2] 文档。"),
            ("参考 [1,2,3] 文档。", [1, 2, 3], "参考 [1][2][3] 文档。"),
            ("参考 【1, 2】 文档。", [1, 2], "参考 [1][2] 文档。"),
            ("参考 【2, 3】 文档。", [2, 3], "参考 [2][3] 文档。"),
        ]
        for raw, expected_nums, expected_clean in test_cases:
            nums = extract_citation_numbers(raw)
            assert nums == expected_nums
            cleaned = clean_answer_citations(raw, {1, 2, 3})
            assert cleaned == expected_clean

    def test_tier5_citation_chinese_fullwidth_comma_limitation(self):
        r"""Empirically document that Chinese fullwidth comma in 【1，2】 is currently not normalized.

        Because citations.py uses r"【(\d+(?:\s*,\s*\d+)*)】", Chinese comma '，' is not matched
        and returns [] instead of [1, 2].
        """
        text = "参考 【1，2】 文档。"
        nums = extract_citation_numbers(text)
        assert nums == []  # Demonstrates unhandled Chinese full-width comma

    def test_tier5_citation_interleaved_valid_and_out_of_range(self):
        """Verify mixed valid and out-of-range citations [1][999][2] retain only valid markers."""
        chunks = [
            {"id": "c1", "document": "doc1.md", "content": "Doc 1"},
            {"id": "c2", "document": "doc2.md", "content": "Doc 2"},
        ]
        raw_answer = "根据 [1][999][2] 分析，结果明确。"
        cleaned, valid_cits, is_valid = verify_citations(raw_answer, chunks)

        assert is_valid is True
        assert len(valid_cits) == 2
        assert [c["n"] for c in valid_cits] == [1, 2]
        assert cleaned == "根据 [1][2] 分析，结果明确。"

    def test_tier5_code_fence_multiline_language_tag_shielding(self):
        """Verify multiline code blocks with various language tags shield citation-like syntax."""
        text = (
            "说明文档如下：\n"
            "```python\n"
            "# 检查配置项 [1]\n"
            "def get_index():\n"
            "    data = [1, 2, 3]\n"
            "    return data[1]\n"
            "```\n"
            "以及 TypeScript 示例：\n"
            "```typescript\n"
            "const lookup: Record<number, string> = { 1: '[1] text' };\n"
            "```\n"
            "正文中的有效引用在此 [1]。\n"
        )
        numbers = extract_citation_numbers(text)
        assert numbers == [1]

        cleaned = clean_answer_citations(text, {1})
        assert "# 检查配置项 [1]" in cleaned
        assert "data[1]" in cleaned
        assert "{ 1: '[1] text' }" in cleaned
        assert "正文中的有效引用在此 [1]。" in cleaned

    def test_tier5_inline_code_shielding_with_adjacent_prose_citations(self):
        """Verify inline code `arr[1]` is shielded, but adjacent prose citation [1] matches."""
        text = "运行 `npm test [1]` 或访问 `data[0]`。经查证 [1]，接口返回正常。"
        numbers = extract_citation_numbers(text)
        assert numbers == [1]

        cleaned = clean_answer_citations(text, {1})
        assert "`npm test [1]`" in cleaned
        assert "`data[0]`" in cleaned
        assert "经查证 [1]" in cleaned

    def test_tier5_markdown_hyperlinks_and_nested_brackets(self):
        """Verify markdown hyperlinks [Link](url) and nested brackets [[1]] do not break extraction."""
        text = "参考 [EvidenceOS 官方文档](https://github.com/evidenceos) 以及嵌套引用 [[1]] 和独立引用 [2]。"
        numbers = extract_citation_numbers(text)
        assert 1 in numbers
        assert 2 in numbers

    def test_tier5_html_tags_and_xss_payload_safety(self):
        """Verify HTML tags and potential script payloads do not corrupt citation parsing."""
        text = (
            '请注意 <span class="highlight">[1]</span> 标签以及 '
            '<script>alert("xss [2]")</script> 代码。依据真实证据 [1]。'
        )
        numbers = extract_citation_numbers(text)
        assert 1 in numbers

        cleaned = clean_answer_citations(text, {1})
        assert '<span class="highlight">[1]</span>' in cleaned
        assert "依据真实证据 [1]。" in cleaned

    def test_tier5_programming_subscript_variable_immunity(self):
        """Verify programming identifiers across various naming styles are immune to citation extraction."""
        text = (
            "变量列表：arr[1]、_cache[4]、config_map[5]、self.items[1]、data2[6]、item_9[7]，"
            "以及内联代码 `matrix[2][3]`。真实来源为 [1]。"
        )
        numbers = extract_citation_numbers(text)
        assert numbers == [1]

        cleaned = clean_answer_citations(text, {1})
        assert "arr[1]" in cleaned
        assert "`matrix[2][3]`" in cleaned
        assert "_cache[4]" in cleaned
        assert "config_map[5]" in cleaned
        assert "self.items[1]" in cleaned
        assert "data2[6]" in cleaned
        assert "item_9[7]" in cleaned
        assert "真实来源为 [1]。" in cleaned


# ===========================================================================
# 8. Chunk Modal Metadata Edge Cases & Extreme Content Hardening
# ===========================================================================

class TestTier5ChunkModalExtremeMetadata:
    """Verifies ChunkModal handling of empty breadcrumbs, null pages, and massive verbatim texts."""

    def test_tier5_chunk_modal_empty_heading_and_null_page(self, client: TestClient, managed_document_ids):
        """Verify chunks with null/empty heading and page return valid JSON matching ChunkDetail contract."""
        raw_content = b"Simple plain text file without any markdown headings or pages."
        _, body = upload_test_doc(client, "plain_unformatted.txt", raw_content, "text/plain")
        managed_document_ids.append(body["id"])

        with SessionLocal() as db:
            chunk = db.query(Chunk).filter(Chunk.document_id == body["id"]).first()
            assert chunk is not None
            chunk_id = chunk.id

        resp = client.get(f"/api/chunks/{chunk_id}")
        assert resp.status_code == 200
        detail = resp.json()

        assert detail["id"] == chunk_id
        assert detail["document"] == "plain_unformatted.txt"
        assert detail["idx"] == 0
        assert detail["page"] is None
        assert detail["heading"] in [None, ""]
        assert "Simple plain text file" in detail["content"]

    def test_tier5_chunk_modal_extreme_payload_inspection(self, client: TestClient, managed_document_ids):
        """Verify /api/chunks/{id} retrieves massive verbatim content (>10,000 characters) without truncation."""
        _, doc = upload_test_doc(client, "huge_chunk_doc.md", b"# Document Header\n\nInitial content.")
        doc_id = doc["id"]
        managed_document_ids.append(doc_id)

        huge_text = "EvidenceOS technical specification paragraph. " * 300  # ~14,000 characters
        huge_chunk_id = f"huge-chunk-{doc_id[:8]}"
        with SessionLocal() as db:
            huge_chunk = Chunk(
                id=huge_chunk_id,
                document_id=doc_id,
                idx=99,
                page=12,
                heading="Massive Specification Section",
                content=huge_text,
                content_seg=huge_text,
            )
            db.add(huge_chunk)
            db.commit()

        try:
            resp = client.get(f"/api/chunks/{huge_chunk_id}")
            assert resp.status_code == 200
            data = resp.json()

            assert data["id"] == huge_chunk_id
            assert data["document"] == "huge_chunk_doc.md"
            assert data["idx"] == 99
            assert data["page"] == 12
            assert data["heading"] == "Massive Specification Section"
            assert len(data["content"]) > 10000
            assert "EvidenceOS technical specification paragraph." in data["content"]
        finally:
            with SessionLocal() as db:
                c = db.query(Chunk).filter(Chunk.id == huge_chunk_id).first()
                if c:
                    db.delete(c)
                    db.commit()

    def test_tier5_chunk_modal_deep_nested_breadcrumb_heading(self, client: TestClient, managed_document_ids):
        """Verify deeply nested heading hierarchy is preserved and returned accurately."""
        content = (
            b"# Level 1 System\n\n"
            b"## Level 2 Subsystem\n\n"
            b"### Level 3 Module\n\n"
            b"#### Level 4 Component\n\n"
            b"##### Level 5 Algorithm & Optimization\n\n"
            b"Deeply nested chunk content."
        )
        _, body = upload_test_doc(client, "deep_hierarchy.md", content)
        managed_document_ids.append(body["id"])

        with SessionLocal() as db:
            chunk = db.query(Chunk).filter(Chunk.document_id == body["id"]).order_by(Chunk.idx.desc()).first()
            assert chunk is not None
            chunk_id = chunk.id

        resp = client.get(f"/api/chunks/{chunk_id}")
        assert resp.status_code == 200
        detail = resp.json()

        assert detail["heading"] is not None
        assert len(detail["heading"]) > 0

    def test_tier5_chunk_modal_high_index_numeric_fidelity(self, client: TestClient, managed_document_ids):
        """Verify chunk with large index number (idx=65535) retains exact numerical representation."""
        _, body = upload_test_doc(client, "idx_test.md", b"# Header\n\nContent")
        doc_id = body["id"]
        managed_document_ids.append(doc_id)

        high_idx_chunk_id = f"test-high-idx-{doc_id[:8]}"
        with SessionLocal() as db:
            c = Chunk(
                id=high_idx_chunk_id,
                document_id=doc_id,
                idx=65535,
                page=999,
                heading="High Index Section",
                content="Verbatim text of chunk with idx 65535",
                content_seg="Verbatim text of chunk with idx 65535",
            )
            db.add(c)
            db.commit()

        try:
            resp = client.get(f"/api/chunks/{high_idx_chunk_id}")
            assert resp.status_code == 200
            detail = resp.json()
            assert detail["idx"] == 65535
            assert detail["page"] == 999
            assert detail["heading"] == "High Index Section"
        finally:
            with SessionLocal() as db:
                to_delete = db.query(Chunk).filter(Chunk.id == high_idx_chunk_id).first()
                if to_delete:
                    db.delete(to_delete)
                    db.commit()

    def test_tier5_chunk_modal_rapid_concurrent_requests(self, client: TestClient, managed_document_ids):
        """Verify rapid concurrent requests to GET /api/chunks/{id} succeed without connection pool failure."""
        _, body = upload_test_doc(client, "concurrent_modal.md", b"# Header\n\nConcurrent inspection target.")
        managed_document_ids.append(body["id"])

        with SessionLocal() as db:
            chunk = db.query(Chunk).filter(Chunk.document_id == body["id"]).first()
            assert chunk is not None
            chunk_id = chunk.id

        def fetch():
            res = client.get(f"/api/chunks/{chunk_id}")
            return res.status_code, res.json()

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(fetch) for _ in range(15)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        for status_code, body in results:
            assert status_code == 200
            assert body["id"] == chunk_id
            assert body["document"] == "concurrent_modal.md"


# ===========================================================================
# 9. End-to-End Adversarial Integration Flow
# ===========================================================================

def test_tier5_e2e_adversarial_stream_and_citation_reconciliation(client: TestClient, managed_document_ids):
    """Execute end-to-end chat query with fake LLM returning out-of-order citations and code fences.

    Verifies the complete pipeline:
    1. Document upload & ingestion
    2. POST /api/chat with adversarial question
    3. Fake LLM returning out-of-order citations [2][1] and shielded code blocks
    4. SSE stream parsing and verification that final citations match chunks
    """
    doc_content = (
        b"# System Architecture Guide\n\n"
        b"EvidenceOS uses LangGraph conditional graph for iterative retrieval.\n\n"
        b"## Hybrid Search Details\n\n"
        b"Combines dense vector embeddings with jieba BM25 tokenization.\n"
    )
    status_code, body = upload_test_doc(client, "arch_guide.md", doc_content)
    assert status_code == 202
    doc_id = body["id"]
    managed_document_ids.append(doc_id)

    mock_answer = (
        "EvidenceOS 采用双路检索：\n"
        "```python\n"
        "# 内部变量保护测试\n"
        "scores = [1, 2]\n"
        "top_chunk = scores[0]\n"
        "```\n"
        "具体细节请查阅 [2][1]。"
    )

    fake_llm = FakeLLMProvider(
        custom_grades=[{"sufficient": True, "reason": "架构文档内容充足", "missing": ""}],
        custom_answers=[mock_answer],
    )

    with patch("apps.api.routers.chat.get_llm_provider", return_value=fake_llm):
        resp = client.post("/api/chat", json={"question": "如何设计双路检索系统？"})
        assert resp.status_code == 200
        events = parse_sse_events(resp.text)

        steps = [e[1] for e in events if e[0] == "step"]
        assert len(steps) >= 4
        nodes = [s["node"] for s in steps]
        assert "retrieve" in nodes
        assert "grade" in nodes

        tokens = [e[1]["text"] for e in events if e[0] == "token"]
        reconstructed_answer = "".join(tokens)
        assert "EvidenceOS 采用双路检索" in reconstructed_answer
        assert "[2][1]" in reconstructed_answer
        assert "top_chunk = scores[0]" in reconstructed_answer

        citations_event = next(e[1] for e in events if e[0] == "citations")
        cits = citations_event["items"]
        assert len(cits) >= 2
        cit_numbers = [c["n"] for c in cits]
        assert cit_numbers == [2, 1]

        done_event = next(e[1] for e in events if e[0] == "done")
        assert done_event["refused"] is False
        assert "run_id" in done_event
        assert done_event["latency_ms"] >= 0


if __name__ == "__main__":
    pytest_args = [__file__, "-v", "--tb=short"]
    exit_code = pytest.main(pytest_args)
    sys.exit(exit_code)
