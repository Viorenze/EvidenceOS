"""Unit tests for the LLM abstraction layer and FakeLLMProvider."""

from pydantic import BaseModel
from apps.api.config import Settings
from apps.api.llm.provider import (
    FakeLLMProvider,
    OpenAILLMProvider,
    get_llm_provider,
)


class SampleSchema(BaseModel):
    name: str
    score: int


def test_fake_llm_generate_default():
    fake = FakeLLMProvider()
    resp = fake.generate([{"role": "user", "content": "你好"}])
    assert "完整支持" in resp
    assert "[1]" in resp
    assert len(fake.call_history) == 1


def test_fake_llm_structured_output():
    fake = FakeLLMProvider(custom_grades=[{"name": "test_grade", "score": 95}])
    res = fake.structured_output([{"role": "user", "content": "evaluate"}], schema=SampleSchema)
    assert res.name == "test_grade"
    assert res.score == 95


def test_fake_llm_rule_based_grading():
    fake = FakeLLMProvider()

    # Rule-based unanswerable
    from apps.api.agent.nodes import GradeSchema

    res_unans = fake.structured_output(
        [{"role": "user", "content": "宇宙飞船在火星的飞行记录是什么？"}],
        schema=GradeSchema,
    )
    assert res_unans.sufficient is False
    assert "未提及" in res_unans.reason

    # Normal question
    res_ans = fake.structured_output(
        [{"role": "user", "content": "FastAPI 如何做依赖注入？"}],
        schema=GradeSchema,
    )
    assert res_ans.sufficient is True


def test_fake_llm_stream_generate():
    fake = FakeLLMProvider(default_answer="测试流式输出")
    chunks = list(fake.stream_generate([{"role": "user", "content": "test"}]))
    assert "".join(chunks) == "测试流式输出"
    assert len(chunks) > 1


def test_openai_llm_provider_init():
    provider = OpenAILLMProvider(
        base_url="https://api.openai.com/v1",
        api_key="test_key",
        model="gpt-4o",
    )
    assert provider.base_url == "https://api.openai.com/v1"
    assert provider.api_key == "test_key"
    assert provider.model == "gpt-4o"
    assert provider._get_headers()["Authorization"] == "Bearer test_key"


def test_get_llm_provider_factory():
    settings = Settings(llm_provider="fake")
    provider = get_llm_provider(settings)
    assert isinstance(provider, FakeLLMProvider)
