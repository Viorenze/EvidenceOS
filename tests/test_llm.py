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


import httpx
import pytest


def test_openai_llm_generate_success():
    def handler(request: httpx.Request):
        assert request.url == "https://api.openai.com/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer test_key"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": "这是生成的回答 [1]"}}
                ]
            },
        )

    provider = OpenAILLMProvider(
        base_url="https://api.openai.com/v1",
        api_key="test_key",
        model="gpt-4o",
        transport=httpx.MockTransport(handler),
    )
    ans = provider.generate([{"role": "user", "content": "你好"}])
    assert ans == "这是生成的回答 [1]"


def test_openai_llm_structured_output_with_markdown_fences():
    def handler(request: httpx.Request):
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": "```json\n{\"name\": \"test_model\", \"score\": 100}\n```"}}
                ]
            },
        )

    provider = OpenAILLMProvider(
        base_url="https://api.openai.com/v1",
        api_key="test_key",
        model="gpt-4o",
        transport=httpx.MockTransport(handler),
    )
    res = provider.structured_output([{"role": "user", "content": "eval"}], schema=SampleSchema)
    assert res.name == "test_model"
    assert res.score == 100


def test_openai_llm_structured_output_malformed_json_raises():
    def handler(request: httpx.Request):
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": "这不是有效的 JSON 格式内容"}}
                ]
            },
        )

    provider = OpenAILLMProvider(
        base_url="https://api.openai.com/v1",
        api_key="test_key",
        model="gpt-4o",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ValueError, match="failed to output valid JSON"):
        provider.structured_output([{"role": "user", "content": "eval"}], schema=SampleSchema)


def test_openai_llm_generate_http_error():
    def handler(request: httpx.Request):
        return httpx.Response(500, text="Internal Server Error")

    provider = OpenAILLMProvider(
        base_url="https://api.openai.com/v1",
        api_key="test_key",
        model="gpt-4o",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(RuntimeError, match="HTTP error 500"):
        provider.generate([{"role": "user", "content": "hello"}])


def test_openai_llm_stream_generate_with_empty_choices():
    def handler(request: httpx.Request):
        # Simulate SSE response stream with content chunks and an empty choices usage chunk
        stream_content = (
            "data: {\"choices\": [{\"delta\": {\"content\": \"Fast\"}}]}\n\n"
            "data: {\"choices\": [{\"delta\": {\"content\": \"API\"}}]}\n\n"
            "data: {\"choices\": []}\n\n"  # Empty choices chunk (e.g. usage info)
            "data: [DONE]\n\n"
        )
        return httpx.Response(
            200,
            content=stream_content.encode("utf-8"),
            headers={"Content-Type": "text/event-stream"},
        )

    provider = OpenAILLMProvider(
        base_url="https://api.openai.com/v1",
        api_key="test_key",
        model="gpt-4o",
        transport=httpx.MockTransport(handler),
    )
    tokens = list(provider.stream_generate([{"role": "user", "content": "hello"}]))
    assert tokens == ["Fast", "API"]


def test_openai_llm_client_lifecycle_and_reuse():
    def handler(request: httpx.Request):
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    mock_transport = httpx.MockTransport(handler)
    provider = OpenAILLMProvider(
        base_url="https://api.openai.com/v1",
        api_key="test_key",
        model="gpt-4o",
        transport=mock_transport,
    )
    # Lazy initialization
    assert provider._client is None
    client_1 = provider._get_client()
    assert client_1 is not None

    # Multiple calls reuse the same client instance
    provider.generate([{"role": "user", "content": "1"}])
    client_2 = provider._get_client()
    assert client_1 is client_2

    # Context manager and close
    with provider:
        pass
    assert provider._client.is_closed


def test_openai_llm_client_default_resilience_config():
    provider = OpenAILLMProvider(
        base_url="https://api.openai.com/v1",
        api_key="test_key",
        model="gpt-4o",
    )
    client = provider._get_client()
    assert not client.is_closed
    # Ensure transport is configured with retries
    transport = client._transport
    assert isinstance(transport, httpx.HTTPTransport)
    assert transport._pool._retries == 2
    provider.close()
    assert client.is_closed
