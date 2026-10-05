"""Agent execution runner and run persistence in PostgreSQL.

Executes the LangGraph conditional agent graph, records execution metrics,
and persists execution history into the `runs` table (citations and steps stored as JSON arrays).
"""

import logging
import time
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from sqlalchemy.orm import Session

from apps.api.agent.graph import create_agent
from apps.api.agent.state import AgentState
from apps.api.config import Settings, get_settings
from apps.api.db.models import Run
from apps.api.llm.provider import LLMProvider

logger = logging.getLogger(__name__)


class RunResult(BaseModel):
    """Execution output returned by run_agent."""

    run_id: str
    question: str
    mode: str
    answer: str
    citations: List[Dict[str, Any]]
    chunks: List[Dict[str, Any]] = []
    steps: List[Dict[str, Any]]
    refused: bool
    latency_ms: float


def run_agent(
    db: Session,
    question: str,
    mode: str = "hybrid",
    llm: Optional[LLMProvider] = None,
    settings: Optional[Settings] = None,
) -> RunResult:
    """Execute the LangGraph agent for a user question and persist to runs table."""
    cfg = settings or get_settings()
    compiled_graph = create_agent(db=db, llm=llm, settings=cfg)

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

    start_time = time.perf_counter()
    run_id = str(uuid.uuid4())
    execution_error: Optional[Exception] = None

    try:
        final_state: Dict[str, Any] = compiled_graph.invoke(initial_state)
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        logger.error("LangGraph agent invocation failed: %s", exc, exc_info=True)
        execution_error = exc
        error_step = {
            "node": "agent",
            "status": "failed",
            "detail": f"Execution failed: {exc}",
        }
        final_state = {
            "answer": "",
            "citations": [],
            "steps": [error_step],
            "refused": False,
        }

    answer_text = final_state.get("answer") or ""
    citations_list = list(final_state.get("citations") or [])
    chunks_list = list(final_state.get("chunks") or [])
    steps_list = list(final_state.get("steps") or [])
    is_refused = bool(final_state.get("refused", False))

    # Best-effort persistence: database errors must not mask execution errors
    try:
        run_record = Run(
            id=run_id,
            question=question,
            mode=mode,
            answer=answer_text,
            citations=citations_list,
            steps=steps_list,
            refused=is_refused,
            latency_ms=round(elapsed_ms, 2),
        )
        db.add(run_record)
        db.commit()
    except Exception as db_exc:
        logger.warning("Failed to persist run record to database (best-effort): %s", db_exc)
        try:
            db.rollback()
        except Exception:
            pass

    # If graph execution failed, re-raise original exception for upstream handling (e.g. SSE error event)
    if execution_error is not None:
        raise execution_error

    return RunResult(
        run_id=run_id,
        question=question,
        mode=mode,
        answer=answer_text,
        citations=citations_list,
        chunks=chunks_list,
        steps=steps_list,
        refused=is_refused,
        latency_ms=round(elapsed_ms, 2),
    )
