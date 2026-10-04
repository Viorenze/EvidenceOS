"""LangGraph state graph definition and compilation for EvidenceOS.

Implements the cyclic conditional loop specified in PRD Section 8:
START → retrieve → grade ──sufficient──→ generate → verify_citations → END
                     │                                    │
                     │insufficient                        └─ 无有效引用：重试一次，仍无则 refuse
                     ├─ rewrites < 2 → rewrite ──→ retrieve
                     └─ rewrites = 2 → refuse → END
"""

import logging
from typing import Literal

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from apps.api.agent.nodes import AgentNodes
from apps.api.agent.state import AgentState
from apps.api.config import Settings, get_settings
from apps.api.llm.provider import LLMProvider, get_llm_provider

logger = logging.getLogger(__name__)


def build_agent_graph(
    db: Session,
    llm: LLMProvider,
    settings: Settings,
) -> StateGraph:
    """Build the compiled LangGraph agent graph with injected dependencies."""
    nodes = AgentNodes(db=db, llm=llm, settings=settings)
    builder = StateGraph(AgentState)

    # 1. Register nodes
    builder.add_node("retrieve", nodes.retrieve_node)
    builder.add_node("grade", nodes.grade_node)
    builder.add_node("rewrite", nodes.rewrite_node)
    builder.add_node("generate", nodes.generate_node)
    builder.add_node("verify_citations", nodes.verify_citations_node)
    builder.add_node("refuse", nodes.refuse_node)

    # 2. Add edges
    builder.add_edge(START, "retrieve")
    builder.add_edge("retrieve", "grade")

    # Conditional edge after grade:
    # - sufficient -> generate
    # - insufficient & rewrites < max_rewrites -> rewrite -> retrieve
    # - insufficient & rewrites >= max_rewrites -> refuse -> END
    def route_after_grade(state: AgentState) -> Literal["generate", "rewrite", "refuse"]:
        grade = state.get("grade") or {}
        if grade.get("sufficient") is True:
            return "generate"
        if state.get("rewrites", 0) < settings.max_rewrites:
            return "rewrite"
        return "refuse"

    builder.add_conditional_edges(
        "grade",
        route_after_grade,
        {
            "generate": "generate",
            "rewrite": "rewrite",
            "refuse": "refuse",
        },
    )

    # Cyclic edge from rewrite back to retrieve
    builder.add_edge("rewrite", "retrieve")

    builder.add_edge("generate", "verify_citations")

    # Conditional edge after verify_citations:
    # - valid citations present -> END
    # - no valid citations & generate_retries <= max_generate_retries -> generate (retry)
    # - no valid citations & retry exhausted -> refuse -> END
    def route_after_verify(state: AgentState) -> Literal["end", "generate", "refuse"]:
        citations = state.get("citations", [])
        if citations:
            return "end"
        if state.get("generate_retries", 0) <= settings.max_generate_retries:
            return "generate"
        return "refuse"

    builder.add_conditional_edges(
        "verify_citations",
        route_after_verify,
        {
            "end": END,
            "generate": "generate",
            "refuse": "refuse",
        },
    )

    builder.add_edge("refuse", END)

    return builder.compile()


def create_agent(
    db: Session,
    llm: LLMProvider | None = None,
    settings: Settings | None = None,
):
    """Convenience helper to create a compiled agent."""
    cfg = settings or get_settings()
    provider = llm or get_llm_provider(cfg)
    return build_agent_graph(db=db, llm=provider, settings=cfg)
