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
    final_state: Dict[str, Any] = compiled_graph.invoke(initial_state)
    elapsed_ms = (time.perf_counter() - start_time) * 1000.0

    run_id = str(uuid.uuid4())
    answer_text = final_state.get("answer") or ""
    citations_list = list(final_state.get("citations") or [])
    steps_list = list(final_state.get("steps") or [])
    is_refused = bool(final_state.get("refused", False))

    # Persist run record to PostgreSQL
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
    db.refresh(run_record)

    return RunResult(
        run_id=run_id,
        question=question,
        mode=mode,
        answer=answer_text,
        citations=citations_list,
        steps=steps_list,
        refused=is_refused,
        latency_ms=round(elapsed_ms, 2),
    )
