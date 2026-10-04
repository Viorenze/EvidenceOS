"""LangGraph agent node implementations for EvidenceOS.

Nodes adhere strictly to PRD Section 8 and AGENTS.md rules:
- retrieve: uses hybrid retrieval
- grade: LLM structured evaluation {sufficient, reason, missing}
- rewrite: query refinement based on missing information
- generate: answer with [n] source citations
- verify_citations: server-side citation validation, stripping invalid markers
- refuse: fixed refusal text, never hallucinating answers with LLM
"""

import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from apps.api.agent.citations import verify_citations
from apps.api.agent.state import AgentState
from apps.api.config import Settings
from apps.api.llm.provider import LLMProvider
from apps.api.rag.retrieval import hybrid_search

logger = logging.getLogger(__name__)


class GradeSchema(BaseModel):
    """Pydantic model for LLM structured grading output."""

    sufficient: bool = Field(
        ...,
        description="检索到的参考文档片段是否包含足够的事实和信息回答用户的问题",
    )
    reason: str = Field(
        ...,
        description="做出充分或不充分判断的简要理由说明",
    )
    missing: str = Field(
        default="",
        description="如果证据不足，指明缺失的关键信息或需要进一步检索的内容",
    )


class AgentNodes:
    """Encapsulates node execution logic with injected dependencies."""

    def __init__(
        self,
        db: Session,
        llm: LLMProvider,
        settings: Settings,
    ) -> None:
        self.db = db
        self.llm = llm
        self.settings = settings

    def retrieve_node(self, state: AgentState) -> Dict[str, Any]:
        """Perform hybrid retrieval using current query."""
        query = state.get("query") or state["question"]
        results = hybrid_search(
            db=self.db,
            query=query,
            top_k=self.settings.final_top_k,
            vector_k=self.settings.vector_top_k,
            fulltext_k=self.settings.fulltext_top_k,
            rrf_k=self.settings.rrf_k,
        )

        chunks_data: List[Dict[str, Any]] = []
        for r in results:
            chunks_data.append({
                "id": r["chunk_id"],
                "document_id": r["document_id"],
                "document_filename": r.get("document", ""),
                "page": r.get("page"),
                "heading": r.get("heading"),
                "content": r["content"],
                "rrf_score": r.get("rrf_score"),
            })

        step = {
            "node": "retrieve",
            "status": "completed",
            "detail": f"Retrieved {len(chunks_data)} chunks for query: '{query}'",
        }

        steps = list(state.get("steps", []))
        steps.append(step)

        return {
            "chunks": chunks_data,
            "steps": steps,
        }

    def grade_node(self, state: AgentState) -> Dict[str, Any]:
        """Evaluate evidence sufficiency using LLM structured output."""
        chunks = state.get("chunks", [])
        question = state["question"]

        if not chunks:
            grade_res = {
                "sufficient": False,
                "reason": "检索结果为空，无任何相关文档",
                "missing": question,
            }
        else:
            # Build context presentation for grading
            context_blocks = []
            for i, c in enumerate(chunks, start=1):
                doc_name = c.get("document_filename", "未知文档")
                heading = c.get("heading") or "无标题"
                context_blocks.append(f"[{i}] 文档: {doc_name} | 章节: {heading}\n{c.get('content', '')}")
            context_str = "\n\n".join(context_blocks)

            system_prompt = (
                "你是一个极其严格的技术文档评估助手。请评估给定的参考文档片段是否足以完整且准确地回答用户的问题。\n"
                "如果参考文档中没有明确的事实依据，或者只包含模糊弱相关的词汇，必须判断为 insufficient (sufficient=false)。\n"
                "输出必须严格符合要求的数据结构。"
            )
            user_prompt = (
                f"用户问题：{question}\n\n"
                f"参考文档片段：\n{context_str}\n\n"
                "请评估证据是否充足："
            )

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]

            grade_obj = self.llm.structured_output(messages, schema=GradeSchema)
            grade_res = grade_obj.model_dump()

        step = {
            "node": "grade",
            "status": "completed",
            "detail": f"Sufficient: {grade_res['sufficient']}. Reason: {grade_res['reason']}",
        }

        steps = list(state.get("steps", []))
        steps.append(step)

        return {
            "grade": grade_res,
            "steps": steps,
        }

    def rewrite_node(self, state: AgentState) -> Dict[str, Any]:
        """Refine the query based on missing information."""
        grade = state.get("grade") or {}
        missing = grade.get("missing", "")
        current_query = state.get("query") or state["question"]
        current_rewrites = state.get("rewrites", 0)

        system_prompt = (
            "你是一个技术文档检索查询改写专家。当检索证据不足时，你需要根据缺失的关键信息，"
            "将原查询改写为更利于技术文档召回的中文关键词或新查询。\n"
            "只输出改写后的查询字符串本身，不要包含任何前缀、引号或解释说明。"
        )
        user_prompt = (
            f"原问题：{state['question']}\n"
            f"原查询：{current_query}\n"
            f"缺失信息：{missing}\n\n"
            "请给出改写后的搜索查询："
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        new_query = self.llm.generate(messages).strip().strip('"').strip("'")
        new_rewrites = current_rewrites + 1

        step = {
            "node": "rewrite",
            "status": "completed",
            "detail": f"Rewrite #{new_rewrites}: '{new_query}' (missing: {missing})",
        }

        steps = list(state.get("steps", []))
        steps.append(step)

        return {
            "query": new_query,
            "rewrites": new_rewrites,
            "steps": steps,
        }

    def generate_node(self, state: AgentState) -> Dict[str, Any]:
        """Generate answer grounded in context chunks with [n] citation markers."""
        chunks = state.get("chunks", [])
        question = state["question"]
        generate_retries = state.get("generate_retries", 0)

        # Number contexts [1]..[k]
        context_blocks = []
        for i, c in enumerate(chunks, start=1):
            doc_name = c.get("document_filename", "未知文档")
            heading = c.get("heading") or "无标题"
            context_blocks.append(f"[{i}] 文档: {doc_name} | 章节: {heading}\n{c.get('content', '')}")
        context_str = "\n\n".join(context_blocks)

        system_prompt = (
            "你是一个严谨的技术知识库问答助手。请仅根据提供的参考文档回答用户的问题。\n"
            "规则：\n"
            "1. 每一个事实、论断或结论后面，必须用 [n] 格式标注其来源文档片段的序号（例如 [1] 或 [2]）。\n"
            "2. 严禁引用不存在的序号（只允许使用提供的 [1] 到 [{len_chunks}] 范围内的有效序号）。\n"
            "3. 绝对不要编造或推测参考文档中没有明确写出的信息。"
        ).format(len_chunks=len(chunks))

        if generate_retries > 0:
            system_prompt += "\n重要提醒：前一次生成未包含合法的引用标记 [n]！请务必在回答中的具体论据后标注 [n] 引用！"

        user_prompt = f"用户问题：{question}\n\n参考文档：\n{context_str}\n\n请给出带引用的回答："

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        raw_answer = self.llm.generate(messages)

        step = {
            "node": "generate",
            "status": "completed",
            "detail": f"Generated answer using {len(chunks)} context chunks (attempt #{generate_retries + 1})",
        }

        steps = list(state.get("steps", []))
        steps.append(step)

        return {
            "answer": raw_answer,
            "steps": steps,
        }

    def verify_citations_node(self, state: AgentState) -> Dict[str, Any]:
        """Validate citations against retrieved chunks and strip invalid markers."""
        answer = state.get("answer") or ""
        chunks = state.get("chunks", [])
        current_retries = state.get("generate_retries", 0)

        cleaned_answer, valid_citations, is_valid = verify_citations(
            answer,
            chunks,
            snippet_chars=getattr(self.settings, "citation_snippet_chars", 200),
        )

        steps = list(state.get("steps", []))

        if is_valid:
            step = {
                "node": "verify_citations",
                "status": "completed",
                "detail": f"Verified {len(valid_citations)} valid citations",
            }
            steps.append(step)
            return {
                "answer": cleaned_answer,
                "citations": valid_citations,
                "steps": steps,
            }
        else:
            new_retries = current_retries + 1
            retry_possible = new_retries <= self.settings.max_generate_retries
            step = {
                "node": "verify_citations",
                "status": "retry_needed" if retry_possible else "failed",
                "detail": f"No valid citations found in answer. Retries attempted: {new_retries}/{self.settings.max_generate_retries}",
            }
            steps.append(step)
            return {
                "answer": cleaned_answer,
                "citations": [],
                "generate_retries": new_retries,
                "steps": steps,
            }

    def refuse_node(self, state: AgentState) -> Dict[str, Any]:
        """Set fixed refusal response without calling LLM (AGENTS.md Rule 7)."""
        refusal_text = self.settings.fixed_refusal_text
        step = {
            "node": "refuse",
            "status": "completed",
            "detail": "Refused due to insufficient evidence or unverified citations",
        }

        steps = list(state.get("steps", []))
        steps.append(step)

        return {
            "answer": refusal_text,
            "refused": True,
            "citations": [],
            "steps": steps,
        }
