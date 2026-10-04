"""State definitions for the EvidenceOS LangGraph Agent.

State structure conforms strictly to PRD Section 8:
`question, query, rewrites, chunks, grade, answer, citations, refused, steps`
plus `generate_retries` for tracking citation verification retry attempts.
"""

from typing import Any, Dict, List, Optional, TypedDict


class AgentStep(TypedDict):
    node: str
    status: str
    detail: str


class CitationItem(TypedDict):
    n: int
    chunk_id: str
    document: str
    page: Optional[int]
    heading: Optional[str]
    snippet: str


class GradeResult(TypedDict):
    sufficient: bool
    reason: str
    missing: str


class AgentState(TypedDict):
    question: str
    query: str
    rewrites: int
    chunks: List[Dict[str, Any]]
    grade: Optional[GradeResult]
    answer: Optional[str]
    citations: List[Dict[str, Any]]
    refused: bool
    steps: List[Dict[str, Any]]
    generate_retries: int
