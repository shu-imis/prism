"""多厂商 LLM 客户端。

封装 OpenAI-compatible 与 Anthropic 调用，提供重试、fallback、JSON
解析修复和可测试的 transport hook。SDK 采用延迟导入，未配置 API Key
时不会影响本地数据库、报告和 UI 基础流程。
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Mapping, Sequence

from config import app_config


Message = Mapping[str, str]
Transport = Callable[["ProviderSettings", Sequence[Message], dict[str, Any]], str]


class LLMProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


@dataclass(frozen=True)
class ProviderSettings:
    """单个模型厂商的运行配置。"""

    provider: LLMProvider
    model: str
    api_key: str | None = None
    base_url: str | None = None


class LLMError(RuntimeError):
    """所有模型厂商均不可用时抛出。"""

    def __init__(self, message: str, failures: list[str] | None = None):
        super().__init__(message)
        self.failures = failures or []


class LLMClient:
    """支持多厂商 fallback 的轻量 LLM 适配器。"""

    def __init__(
        self,
        provider: LLMProvider | None = None,
        model: str | None = None,
        api_key: str | None = None,
        temperature: float | None = None,
        max_retries: int | None = None,
        timeout: int | None = None,
        providers: Sequence[ProviderSettings] | None = None,
        transport: Transport | None = None,
        retry_base_seconds: float = 0.4,
    ):
        self.providers = list(providers or [])
        if not self.providers:
            self.providers = [
                ProviderSettings(
                    provider=provider or LLMProvider.OPENAI,
                    model=model or app_config.llm.default_model,
                    api_key=api_key,
                    base_url=os.getenv("OPENAI_BASE_URL"),
                )
            ]
        self.temperature = app_config.llm.temperature if temperature is None else temperature
        self.max_retries = app_config.llm.max_retries if max_retries is None else max_retries
        self.timeout = app_config.llm.request_timeout if timeout is None else timeout
        self.retry_base_seconds = retry_base_seconds
        self._transport = transport

    @classmethod
    def from_env(
        cls,
        prefer: LLMProvider = LLMProvider.OPENAI,
        openai_key: str | None = None,
        anthropic_key: str | None = None,
    ) -> "LLMClient":
        """从环境变量创建客户端，自动按可用 Key 配置 fallback 顺序。"""

        oai_key = openai_key or os.getenv("OPENAI_API_KEY")
        ant_key = anthropic_key or os.getenv("ANTHROPIC_API_KEY")

        preferred = [LLMProvider.OPENAI, LLMProvider.ANTHROPIC]
        if prefer == LLMProvider.ANTHROPIC:
            preferred.reverse()

        providers: list[ProviderSettings] = []
        for provider in preferred:
            if provider == LLMProvider.OPENAI and oai_key:
                providers.append(
                    ProviderSettings(
                        LLMProvider.OPENAI,
                        os.getenv("OPENAI_MODEL") or os.getenv("LLM_DEFAULT_MODEL", app_config.llm.default_model),
                        oai_key,
                        os.getenv("OPENAI_BASE_URL"),
                    )
                )
            if provider == LLMProvider.ANTHROPIC and ant_key:
                providers.append(
                    ProviderSettings(
                        LLMProvider.ANTHROPIC,
                        os.getenv("ANTHROPIC_MODEL", "claude-fable-5"),
                        ant_key,
                    )
                )
        if not providers:
            raise LLMError("未找到可用的 LLM API Key，请设置 OPENAI_API_KEY 或 ANTHROPIC_API_KEY")
        return cls(providers=providers)

    def chat(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float | None = None,
    ) -> str:
        """传入 system prompt 与 user message，返回纯文本。"""

        return self.chat_messages(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=temperature,
        )

    def chat_messages(
        self,
        messages: Sequence[Message],
        *,
        temperature: float | None = None,
        max_tokens: int = 4096,
        json_mode: bool = False,
    ) -> str:
        """按配置顺序请求模型，单厂商失败后自动切换下一厂商。"""

        options = {
            "temperature": self.temperature if temperature is None else temperature,
            "max_tokens": max_tokens,
            "timeout": self.timeout,
            "json_mode": json_mode,
        }
        failures: list[str] = []

        for provider in self.providers:
            for attempt in range(self.max_retries + 1):
                try:
                    if self._transport:
                        return self._transport(provider, messages, options)
                    return self._call_sdk(provider, messages, options)
                except Exception as exc:  # noqa: BLE001 - 第三方 SDK 错误类型不统一
                    failures.append(f"{provider.provider.value} attempt {attempt + 1}: {exc}")
                    if attempt < self.max_retries:
                        time.sleep(self.retry_base_seconds * (2**attempt))
                    else:
                        break

        raise LLMError("所有已配置的 LLM 厂商均调用失败", failures)

    def chat_json(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float | None = 0.2,
    ) -> dict[str, Any]:
        """请求 JSON 对象并解析（带容错修复）。"""

        raw = self.chat_messages(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=temperature,
            json_mode=True,
        )
        parsed = parse_json_object(raw)
        if not isinstance(parsed, dict):
            raise ValueError("LLM JSON 响应必须是对象")
        return parsed

    def _call_sdk(
        self,
        provider: ProviderSettings,
        messages: Sequence[Message],
        options: dict[str, Any],
    ) -> str:
        if provider.provider == LLMProvider.OPENAI:
            return self._call_openai(provider, messages, options)
        if provider.provider == LLMProvider.ANTHROPIC:
            return self._call_anthropic(provider, messages, options)
        raise ValueError(f"不支持的 LLM 厂商: {provider.provider}")

    @staticmethod
    def _call_openai(
        provider: ProviderSettings,
        messages: Sequence[Message],
        options: dict[str, Any],
    ) -> str:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("openai 包未安装。运行: pip install openai") from exc

        kwargs: dict[str, Any] = {"api_key": provider.api_key, "timeout": options["timeout"]}
        if provider.base_url:
            kwargs["base_url"] = provider.base_url

        request: dict[str, Any] = {
            "model": provider.model,
            "messages": list(messages),
            "temperature": options["temperature"],
            "max_tokens": options["max_tokens"],
        }
        if options.get("json_mode"):
            request["response_format"] = {"type": "json_object"}

        response = OpenAI(**kwargs).chat.completions.create(**request)
        return strip_model_noise(response.choices[0].message.content or "")

    @staticmethod
    def _call_anthropic(
        provider: ProviderSettings,
        messages: Sequence[Message],
        options: dict[str, Any],
    ) -> str:
        try:
            from anthropic import Anthropic
        except ImportError as exc:
            raise RuntimeError("anthropic 包未安装。运行: pip install anthropic") from exc

        system_prompt = ""
        user_messages: list[dict[str, str]] = []
        for message in messages:
            if message.get("role") == "system":
                system_prompt = message.get("content", "")
            else:
                user_messages.append(
                    {
                        "role": "assistant" if message.get("role") == "assistant" else "user",
                        "content": message.get("content", ""),
                    }
                )

        kwargs: dict[str, Any] = {"api_key": provider.api_key, "timeout": options["timeout"]}
        if provider.base_url:
            kwargs["base_url"] = provider.base_url

        response = Anthropic(**kwargs).messages.create(
            model=provider.model,
            system=system_prompt,
            messages=user_messages,
            temperature=options["temperature"],
            max_tokens=options["max_tokens"],
        )
        return strip_model_noise("\n".join(getattr(block, "text", "") for block in response.content))


def strip_model_noise(text: str) -> str:
    """移除常见模型思考标签和外层空白。"""

    return re.sub(r"<think>[\s\S]*?</think>", "", text).strip()


def parse_json_object(raw: str) -> Any:
    """从模型输出中解析 JSON，兼容代码块、前后解释文字和尾逗号。"""

    cleaned = strip_model_noise(raw).strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    candidate = _extract_balanced_json(cleaned)
    if not candidate:
        raise ValueError(f"无法从 LLM 返回中定位 JSON: {raw[:200]}")

    candidate = re.sub(r",(\s*[}\]])", r"\1", candidate)
    return json.loads(candidate)


def _extract_balanced_json(text: str) -> str | None:
    starts = [idx for idx, ch in enumerate(text) if ch in "[{"]
    for start in starts:
        stack: list[str] = []
        in_string = False
        escape = False
        for idx in range(start, len(text)):
            ch = text[idx]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch in "[{":
                stack.append("]" if ch == "[" else "}")
            elif ch in "]}":
                if not stack or stack.pop() != ch:
                    break
                if not stack:
                    return text[start : idx + 1]
    return None
