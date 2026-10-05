"""Unit and integration tests for the LangGraph Agent and Run persistence."""

from unittest.mock import MagicMock, patch
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.agent.graph import build_agent_graph
from apps.api.agent.runner import run_agent
from apps.api.agent.state import AgentState
from apps.api.config import Settings
from apps.api.db.models import Run
from apps.api.db.session import engine
from apps.api.llm.provider import FakeLLMProvider


MOCK_CHUNKS = [
    {
        "chunk_id": "chunk-test-1",
        "document_id": "doc-test-1",
        "document": "fastapi_overview.md",
        "page": 1,
        "heading": "Dependency Injection",
        "content": "FastAPI 原生支持依赖注入系统，通过 Depends 声明。",
        "rrf_score": 0.033,
    },
    {
        "chunk_id": "chunk-test-2",
        "document_id": "doc-test-1",
        "document": "fastapi_overview.md",
        "page": 2,
        "heading": "Model Switch",
        "content": "通过配置 EMBEDDING_PROVIDER 即可切换本地与接口。",
        "rrf_score": 0.031,
    },
]


def is_postgres_available() -> bool:
    """Check if PostgreSQL is reachable."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1;"))
            return True
    except Exception:
        return False


@pytest.fixture
def agent_settings():
    return Settings(
        embedding_provider="fake",
        llm_provider="fake",
        final_top_k=3,
        max_rewrites=2,
        max_generate_retries=1,
        fixed_refusal_text="根据已有知识库内容，无法回答该问题。",
    )


@patch("apps.api.agent.nodes.hybrid_search", return_value=MOCK_CHUNKS)
def test_agent_path_answerable_direct_success(mock_search, agent_settings: Settings):
    """Path 1: retrieve -> grade(sufficient) -> generate -> verify_citations -> END."""
    fake_llm = FakeLLMProvider(
        custom_grades=[{"sufficient": True, "reason": "检索到的内容充分", "missing": ""}],
        custom_answers=["FastAPI 原生支持依赖注入 [1]。"],
    )

    mock_db = MagicMock(spec=Session)
    app = build_agent_graph(db=mock_db, llm=fake_llm, settings=agent_settings)
    initial_state: AgentState = {
        "question": "FastAPI 如何做依赖注入？",
        "query": "FastAPI 如何做依赖注入？",
        "rewrites": 0,
        "chunks": [],
        "grade": None,
        "answer": None,
        "citations": [],
        "refused": False,
        "steps": [],
        "generate_retries": 0,
    }

    result = app.invoke(initial_state)

    assert result["refused"] is False
    assert "FastAPI 原生支持依赖注入 [1]" in result["answer"]
    assert len(result["citations"]) >= 1
    assert result["citations"][0]["n"] == 1
    assert result["rewrites"] == 0

    nodes_executed = [s["node"] for s in result["steps"]]
    assert nodes_executed == ["retrieve", "grade", "generate", "verify_citations"]


@patch("apps.api.agent.nodes.hybrid_search", return_value=MOCK_CHUNKS)
def test_agent_path_rewrite_then_succeed(mock_search, agent_settings: Settings):
    """Path 2: retrieve -> grade(insufficient) -> rewrite -> retrieve -> grade(sufficient) -> generate -> verify -> END."""
    fake_llm = FakeLLMProvider(
        custom_grades=[
            {"sufficient": False, "reason": "证据不足，缺少配置详情", "missing": "配置项的具体定义"},
            {"sufficient": True, "reason": "补充检索后证据充分", "missing": ""},
        ],
        custom_answers=[
            "检索改写查询",  # rewrite answer
            "通过配置 EMBEDDING_PROVIDER 即可切换本地与接口 [1]。",  # generate answer
        ],
    )

    mock_db = MagicMock(spec=Session)
    app = build_agent_graph(db=mock_db, llm=fake_llm, settings=agent_settings)
    initial_state: AgentState = {
        "question": "怎么切换 embedding 模型？",
        "query": "怎么切换 embedding 模型？",
        "rewrites": 0,
        "chunks": [],
        "grade": None,
        "answer": None,
        "citations": [],
        "refused": False,
        "steps": [],
        "generate_retries": 0,
    }

    result = app.invoke(initial_state)

    assert result["refused"] is False
    assert result["rewrites"] == 1
    assert len(result["citations"]) >= 1

    nodes_executed = [s["node"] for s in result["steps"]]
    assert nodes_executed == ["retrieve", "grade", "rewrite", "retrieve", "grade", "generate", "verify_citations"]


@patch("apps.api.agent.nodes.hybrid_search", return_value=MOCK_CHUNKS)
def test_agent_path_unanswerable_max_rewrites_refusal(mock_search, agent_settings: Settings):
    """Path 3: retrieve -> grade(insufficient) -> rewrite (1) -> retrieve -> grade -> rewrite (2) -> retrieve -> grade -> refuse -> END."""
    fake_llm = FakeLLMProvider(
        custom_grades=[
            {"sufficient": False, "reason": "未找到相关技术方案", "missing": "量子计算支持"},
            {"sufficient": False, "reason": "仍未找到相关方案", "missing": "量子计算支持"},
            {"sufficient": False, "reason": "三次检索均无证据", "missing": "量子计算支持"},
        ],
        custom_answers=[
            "改写 1",
            "改写 2",
        ],
    )

    mock_db = MagicMock(spec=Session)
    app = build_agent_graph(db=mock_db, llm=fake_llm, settings=agent_settings)
    initial_state: AgentState = {
        "question": "FastAPI 如何接入超导量子计算机？",
        "query": "FastAPI 如何接入超导量子计算机？",
        "rewrites": 0,
        "chunks": [],
        "grade": None,
        "answer": None,
        "citations": [],
        "refused": False,
        "steps": [],
        "generate_retries": 0,
    }

    result = app.invoke(initial_state)

    assert result["refused"] is True
    assert result["answer"] == agent_settings.fixed_refusal_text
    assert result["citations"] == []
    assert result["rewrites"] == 2

    nodes_executed = [s["node"] for s in result["steps"]]
    assert nodes_executed == [
        "retrieve", "grade", "rewrite",
        "retrieve", "grade", "rewrite",
        "retrieve", "grade", "refuse"
    ]


@patch("apps.api.agent.nodes.hybrid_search", return_value=MOCK_CHUNKS)
def test_agent_citation_retry_exhausted_to_refusal(mock_search, agent_settings: Settings):
    """Path 4: generate -> verify_citations (fail) -> generate (retry 1) -> verify_citations (fail) -> refuse -> END."""
    fake_llm = FakeLLMProvider(
        custom_grades=[{"sufficient": True, "reason": "证据充足", "missing": ""}],
        # Both generation attempts fail to provide valid citations
        custom_answers=[
            "第一次生成没有任何引用标记。",
            "第二次重试依然没有任何引用标记。",
        ],
    )

    mock_db = MagicMock(spec=Session)
    app = build_agent_graph(db=mock_db, llm=fake_llm, settings=agent_settings)
    initial_state: AgentState = {
        "question": "测试引用重试失败",
        "query": "测试引用重试失败",
        "rewrites": 0,
        "chunks": [],
        "grade": None,
        "answer": None,
        "citations": [],
        "refused": False,
        "steps": [],
        "generate_retries": 0,
    }

    result = app.invoke(initial_state)

    assert result["refused"] is True
    assert result["answer"] == agent_settings.fixed_refusal_text
    assert result["citations"] == []

    nodes_executed = [s["node"] for s in result["steps"]]
    assert nodes_executed == [
        "retrieve", "grade",
        "generate", "verify_citations",
        "generate", "verify_citations",
        "refuse"
    ]


@patch("apps.api.agent.nodes.hybrid_search", return_value=MOCK_CHUNKS)
def test_agent_citation_retry_succeeds_on_second_attempt(mock_search, agent_settings: Settings):
    """Path 5: generate (no cit) -> verify (fail) -> generate (has cit [1]) -> verify (pass) -> END."""
    fake_llm = FakeLLMProvider(
        custom_grades=[{"sufficient": True, "reason": "证据充足", "missing": ""}],
        custom_answers=[
            "第一次生成遗漏了引用标记。",
            "第二次重试成功补上了合法引用 [1]。",
        ],
    )

    mock_db = MagicMock(spec=Session)
    app = build_agent_graph(db=mock_db, llm=fake_llm, settings=agent_settings)
    initial_state: AgentState = {
        "question": "测试引用重试成功",
        "query": "测试引用重试成功",
        "rewrites": 0,
        "chunks": [],
        "grade": None,
        "answer": None,
        "citations": [],
        "refused": False,
        "steps": [],
        "generate_retries": 0,
    }

    result = app.invoke(initial_state)

    assert result["refused"] is False
    assert "第二次重试成功补上了合法引用 [1]" in result["answer"]
    assert len(result["citations"]) == 1
    assert result["citations"][0]["n"] == 1

    nodes_executed = [s["node"] for s in result["steps"]]
    assert nodes_executed == [
        "retrieve", "grade",
        "generate", "verify_citations",
        "generate", "verify_citations",
    ]


@patch("apps.api.agent.nodes.hybrid_search", return_value=MOCK_CHUNKS)
def test_agent_cleans_illegal_citation_markers(mock_search, agent_settings: Settings):
    """Path 6: Model emits [1] and illegal [99] -> answer retains [1], strips [99]."""
    fake_llm = FakeLLMProvider(
        custom_grades=[{"sufficient": True, "reason": "证据充足", "missing": ""}],
        custom_answers=[
            "文档证实了该特性 [1]，但某额外推测无效 [99]。",
        ],
    )

    mock_db = MagicMock(spec=Session)
    app = build_agent_graph(db=mock_db, llm=fake_llm, settings=agent_settings)
    initial_state: AgentState = {
        "question": "测试清理悬空引用",
        "query": "测试清理悬空引用",
        "rewrites": 0,
        "chunks": [],
        "grade": None,
        "answer": None,
        "citations": [],
        "refused": False,
        "steps": [],
        "generate_retries": 0,
    }

    result = app.invoke(initial_state)

    assert result["refused"] is False
    assert "[1]" in result["answer"]
    assert "[99]" not in result["answer"]
    assert len(result["citations"]) == 1
    assert result["citations"][0]["n"] == 1


@patch("apps.api.agent.nodes.hybrid_search", return_value=MOCK_CHUNKS)
@pytest.mark.integration
def test_run_agent_persistence_in_db(mock_search, agent_settings: Settings):
    """Path 7: run_agent execution stores run record into PostgreSQL with JSON arrays."""
    if not is_postgres_available():
        pytest.skip("PostgreSQL + pgvector is not currently reachable")

    from apps.api.db.session import SessionLocal, init_db
    init_db()
    db = SessionLocal()

    try:
        fake_llm = FakeLLMProvider(
            custom_grades=[{"sufficient": True, "reason": "检索证据充足", "missing": ""}],
            custom_answers=["FastAPI 性能极高 [1]。"],
        )

        res = run_agent(
            db=db,
            question="FastAPI 性能如何？",
            mode="hybrid",
            llm=fake_llm,
            settings=agent_settings,
        )

        assert res.run_id is not None
        assert res.refused is False
        assert res.latency_ms > 0
        assert len(res.citations) >= 1
        assert isinstance(res.citations, list)
        assert isinstance(res.steps, list)

        # Query from database to verify persistence
        db_run = db.query(Run).filter(Run.id == res.run_id).first()
        assert db_run is not None
        assert db_run.question == "FastAPI 性能如何？"
        assert db_run.mode == "hybrid"
        assert db_run.refused is False
        assert db_run.latency_ms > 0
        assert isinstance(db_run.citations, list)
        assert isinstance(db_run.steps, list)
        assert len(db_run.citations) >= 1
        assert len(db_run.steps) >= 4

        # Clean up inserted test record to keep test isolated
        db.delete(db_run)
        db.commit()
    finally:
        db.close()


def test_run_agent_graph_failure_re_raises_and_persists_best_effort(agent_settings: Settings):
    """Verify runner re-raises original graph error and ensures DB failures do not mask it."""
    mock_db = MagicMock(spec=Session)
    # Simulate DB crashing on commit
    mock_db.commit.side_effect = Exception("DB connection crashed")

    fake_llm = FakeLLMProvider()

    with patch("apps.api.agent.runner.create_agent") as mock_create:
        mock_graph = MagicMock()
        mock_graph.invoke.side_effect = RuntimeError("Upstream LLM network timeout")
        mock_create.return_value = mock_graph

        with pytest.raises(RuntimeError, match="Upstream LLM network timeout"):
            run_agent(
                db=mock_db,
                question="测试错误传播",
                mode="hybrid",
                llm=fake_llm,
                settings=agent_settings,
            )

    # Verify rollback was attempted on DB failure without overwriting the original exception
    assert mock_db.rollback.called


