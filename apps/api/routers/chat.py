"""Chat endpoint delivering Server-Sent Events (SSE) stream for EvidenceOS.

Why this SSE implementation works (Interview Reference):
1. Verify-then-stream token delivery:
   To maintain verifiable citations and eliminate dangling/hallucinated markers,
   the agent graph fully completes generation and server-side citation validation.
   Tokens pushed via SSE are strictly sliced from the verified final answer.
2. Real-time agent progress with LangGraph streaming:
   Uses `compiled_graph.stream(..., stream_mode="updates")` to capture intermediate
   node completion events (`retrieve` -> `grade` -> `rewrite`...) in real time.
3. Strict SSE schema conformity:
   Emits `step`, `token`, `citations`, `done`, and `error` events matching PRD Section 6.
"""

import json
import logging
import time
import uuid
from typing import Any, Dict, Iterator, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from apps.api.agent.graph import create_agent
from apps.api.agent.state import AgentState
from apps.api.config import Settings, get_settings
from apps.api.db.models import Run
from apps.api.db.session import SessionLocal, get_db
from apps.api.llm.provider import LLMProvider, get_llm_provider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])


class ChatRequest(BaseModel):
    question: str


def format_sse(event: str, data: Any) -> str:
    """Format SSE frame conforming to standard 'event: <name>\\ndata: <json>\\n\\n'."""
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


def stream_chat_events(
    question: str,
    settings: Optional[Settings] = None,
    llm: Optional[LLMProvider] = None,
    db: Optional[Session] = None,
) -> Iterator[str]:
    """Execute LangGraph agent stream and bridge node transitions and verified answers to SSE."""
    cfg = settings or get_settings()
    provider = llm or get_llm_provider(cfg)
    start_time = time.perf_counter()
    run_id = str(uuid.uuid4())

    close_db = False
    session = db
    if session is None:
        session = SessionLocal()
        close_db = True

    try:
        compiled_graph = create_agent(db=session, llm=provider, settings=cfg)

        initial_state: AgentState = {
            "question": question,
            "query": question,
            "rewrites": 0,
            "chunks": [],
            "grade": None,
            "answer": None,
            "citations": [],
            "refused": False,
            "steps": [],
            "generate_retries": 0,
        }

        final_answer = ""
        final_citations: List[Dict[str, Any]] = []
        is_refused = False
        accumulated_steps: List[Dict[str, Any]] = []

        # Emit immediate initial status step to guarantee TTFB < 50ms and provide instant UI feedback
        init_step = {
            "node": "retrieve",
            "status": "running",
            "detail": f"正在检索知识库文档: '{question[:25]}...'" if len(question) > 25 else f"正在检索知识库文档: '{question}'",
        }
        accumulated_steps.append(init_step)
        yield format_sse("step", init_step)

        # 1. Stream intermediate node updates using LangGraph stream adapter
        for update in compiled_graph.stream(initial_state, stream_mode="updates"):
            for node_name, node_output in update.items():
                node_steps = node_output.get("steps") or []
                if node_steps:
                    latest_step = node_steps[-1]
                    accumulated_steps.append(latest_step)
                    yield format_sse("step", latest_step)

                if "answer" in node_output and node_output["answer"]:
                    final_answer = node_output["answer"]
                if "citations" in node_output:
                    final_citations = list(node_output["citations"])
                if node_output.get("refused") is True or node_name == "refuse":
                    is_refused = True
                    final_answer = cfg.fixed_refusal_text

        # 2. Verify-then-stream token delivery (server-side verified answer slices)
        chunk_size = 4
        for i in range(0, len(final_answer), chunk_size):
            token_slice = final_answer[i : i + chunk_size]
            yield format_sse("token", {"text": token_slice})

        # 3. Emit verified citations metadata
        yield format_sse("citations", {"items": final_citations})

        elapsed_ms = round((time.perf_counter() - start_time) * 1000.0, 2)

        # 4. Persistence in runs table (guarantee persistence succeeded before emitting done)
        try:
            run_record = Run(
                id=run_id,
                question=question,
                mode="hybrid",
                answer=final_answer,
                citations=final_citations,
                steps=accumulated_steps,
                refused=is_refused,
                latency_ms=elapsed_ms,
            )
            session.add(run_record)
            session.commit()
        except Exception as db_exc:
            logger.error("Failed to persist run in database: %s", db_exc, exc_info=True)
            try:
                session.rollback()
            except Exception:
                pass
            yield format_sse("error", {"message": f"Database persistence failed: {db_exc}"})
            return

        # 5. Emit done event
        yield format_sse("done", {
            "run_id": run_id,
            "refused": is_refused,
            "latency_ms": elapsed_ms,
        })

    except Exception as exc:
        logger.error("Error during chat stream: %s", exc, exc_info=True)
        yield format_sse("error", {"message": str(exc)})
    finally:
        if close_db and session is not None:
            session.close()


@router.post("/chat")
def chat_endpoint(request: ChatRequest, db: Session = Depends(get_db)):
    """Deliver streamed answer with verifiable citations and node steps via SSE."""
    q = request.question.strip()
    if not q:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Question cannot be empty",
        )

    return StreamingResponse(
        stream_chat_events(question=q, db=db),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
