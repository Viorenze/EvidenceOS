"""LLM Provider abstraction layer.

All LLM calls throughout EvidenceOS must pass through this module (AGENTS.md Rule 2).
Supports OpenAI-compatible APIs (DeepSeek, Qwen, etc.) and a deterministic FakeLLMProvider
for offline testing without external network calls or API keys.
"""

import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, Iterator, List, Optional, Type, TypeVar

import httpx
from pydantic import BaseModel

from apps.api.config import Settings, get_settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    def generate(self, messages: List[Dict[str, str]], temperature: float = 0.0) -> str:
        """Generate complete response text non-streamingly."""
        pass

    @abstractmethod
    def structured_output(
        self, messages: List[Dict[str, str]], schema: Type[T], temperature: float = 0.0
    ) -> T:
        """Generate structured output validated against a Pydantic schema."""
        pass

    @abstractmethod
    def stream_generate(
        self, messages: List[Dict[str, str]], temperature: float = 0.0
    ) -> Iterator[str]:
        """Stream response tokens chunk by chunk (forward-compatible for D4 SSE)."""
        pass


def _clean_json_markdown(text: str) -> str:
    """Extract raw JSON string from potential markdown code blocks."""
    cleaned = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
    if match:
        return match.group(1).strip()
    return cleaned


class OpenAILLMProvider(LLMProvider):
    """OpenAI-compatible HTTP provider using httpx."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def _get_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def generate(self, messages: List[Dict[str, str]], temperature: float = 0.0) -> str:
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(url, json=payload, headers=self._get_headers())
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    def structured_output(
        self, messages: List[Dict[str, str]], schema: Type[T], temperature: float = 0.0
    ) -> T:
        """Ask model for JSON output conforming to schema and parse it with Pydantic."""
        schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        system_instruction = (
            f"\n请务必只输出符合以下 JSON Schema 的纯 JSON 对象，不要输出任何多余说明或 Markdown 标签：\n{schema_json}"
        )

        augmented_messages = list(messages)
        if augmented_messages and augmented_messages[0]["role"] == "system":
            augmented_messages[0] = {
                "role": "system",
                "content": augmented_messages[0]["content"] + system_instruction,
            }
        else:
            augmented_messages.insert(0, {"role": "system", "content": system_instruction})

        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": augmented_messages,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(url, json=payload, headers=self._get_headers())
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]

        clean_content = _clean_json_markdown(content)
        parsed_dict = json.loads(clean_content)
        return schema.model_validate(parsed_dict)

    def stream_generate(
        self, messages: List[Dict[str, str]], temperature: float = 0.0
    ) -> Iterator[str]:
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        with httpx.Client(timeout=self.timeout) as client:
            with client.stream("POST", url, json=payload, headers=self._get_headers()) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line:
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk_data = json.loads(data_str)
                            delta = chunk_data["choices"][0]["delta"]
                            if "content" in delta and delta["content"]:
                                yield delta["content"]
                        except json.JSONDecodeError:
                            continue


class FakeLLMProvider(LLMProvider):
    """Deterministic Fake LLM provider for offline testing and CI.

    Supports configurable responses, custom hooks, and rule-based handling
    for grading, query rewrite, answer generation, and citation simulation.
    """

    def __init__(
        self,
        default_answer: Optional[str] = None,
        custom_grades: Optional[List[Dict[str, Any]]] = None,
        custom_answers: Optional[List[str]] = None,
    ) -> None:
        self.default_answer = default_answer or "根据文档说明，该功能已获得完整支持 [1]。"
        self.custom_grades = list(custom_grades or [])
        self.custom_answers = list(custom_answers or [])
        self.call_history: List[Dict[str, Any]] = []

    def generate(self, messages: List[Dict[str, str]], temperature: float = 0.0) -> str:
        self.call_history.append({"type": "generate", "messages": messages})

        # If custom answer list has items, pop the first
        if self.custom_answers:
            return self.custom_answers.pop(0)

        # Inspect prompt for simulation markers
        prompt_text = " ".join(m.get("content", "") for m in messages)

        # Check for citation failure test markers
        if "[TEST_INVALID_CITATION]" in prompt_text:
            return "根据文档信息，这是一个无效引用测试 [99]。"
        if "[TEST_NO_CITATION]" in prompt_text:
            return "根据文档信息，这里没有任何引用标记。"
        if "[TEST_RETRY_ONCE_THEN_SUCCEED]" in prompt_text:
            # Check how many times generate was called
            gen_calls = [c for c in self.call_history if c["type"] == "generate"]
            if len(gen_calls) == 1:
                return "初次生成未包含引用。"
            return "重试生成包含了合法引用 [1]。"

        # Check if prompt is a rewrite prompt
        if "改写" in prompt_text or "rewrite" in prompt_text.lower():
            # Extract query to rewrite if possible
            match = re.search(r"原查询[：:]\s*(.*?)(?:\n|$)", prompt_text)
            orig = match.group(1).strip() if match else "优化查询"
            return f"{orig} 补充检索关键词"

        return self.default_answer

    def structured_output(
        self, messages: List[Dict[str, str]], schema: Type[T], temperature: float = 0.0
    ) -> T:
        self.call_history.append({"type": "structured_output", "messages": messages, "schema": schema.__name__})

        if self.custom_grades:
            val = self.custom_grades.pop(0)
            return schema.model_validate(val)

        prompt_text = " ".join(m.get("content", "") for m in messages)

        # Rule-based decision for grading
        # If question contains unanswerable markers or keywords
        unanswerable_keywords = [
            "unanswerable",
            "不可回答",
            "量子纠缠",
            "火星移民",
            "不存在的功能",
            "宇宙飞船",
            "TEST_GRADE_INSUFFICIENT",
        ]
        is_unanswerable = any(kw in prompt_text for kw in unanswerable_keywords)

        if "[TEST_REWRITE_THEN_SUCCEED]" in prompt_text:
            # First grade returns insufficient, subsequent returns sufficient
            grade_calls = [c for c in self.call_history if c["type"] == "structured_output"]
            if len(grade_calls) == 1:
                return schema.model_validate({
                    "sufficient": False,
                    "reason": "证据不足，缺少具体配置参数说明",
                    "missing": "配置参数的具体用法",
                })
            return schema.model_validate({
                "sufficient": True,
                "reason": "经过改写后检索到的证据充足",
                "missing": "",
            })

        if is_unanswerable:
            return schema.model_validate({
                "sufficient": False,
                "reason": "现有文档中未提及该内容",
                "missing": "相关的核心定义与使用说明",
            })

        # Default for answerable questions
        return schema.model_validate({
            "sufficient": True,
            "reason": "检索到的文档片段包含了回答所需的关键信息",
            "missing": "",
        })

    def stream_generate(
        self, messages: List[Dict[str, str]], temperature: float = 0.0
    ) -> Iterator[str]:
        full_text = self.generate(messages, temperature)
        # Yield character by character or in words to simulate stream
        chunk_size = 4
        for i in range(0, len(full_text), chunk_size):
            yield full_text[i : i + chunk_size]


def get_llm_provider(settings: Optional[Settings] = None) -> LLMProvider:
    """Factory to get the configured LLM provider (AGENTS.md Rule 2)."""
    cfg = settings or get_settings()
    if cfg.llm_provider == "fake":
        return FakeLLMProvider()
    return OpenAILLMProvider(
        base_url=cfg.llm_base_url,
        api_key=cfg.llm_api_key,
        model=cfg.llm_model,
        timeout=cfg.llm_timeout_seconds,
    )
