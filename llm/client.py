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


# SDK 客户端实例缓存：以 (provider, api_key, base_url) 为键复用连接池。
# dict 读写对并发足够安全（最坏情况是多建一个实例）。
_client_cache: dict = {}


def _get_sdk_client(key: tuple, factory: Callable[[], Any]) -> Any:
    if key not in _client_cache:
        _client_cache[key] = factory()
    return _client_cache[key]


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
                    text, truncated = self._call_sdk(provider, messages, options)
                    # 响应被 max_tokens 截断：放大到 8192 重试一次（仅一次，不走 max_retries 循环）
                    if truncated and options["max_tokens"] < 8192:
                        options = {**options, "max_tokens": 8192}
                        text, _ = self._call_sdk(provider, messages, options)
                    return text
                except Exception as exc:  # noqa: BLE001 - 第三方 SDK 错误类型不统一
                    failures.append(f"{provider.provider.value} attempt {attempt + 1}: {exc}")
                    # 错误分类（OpenAI/Anthropic SDK 的 APIStatusError 均带 status_code）：
                    # 4xx 永久性错误重试无意义，直接 break 切换下一个厂商
                    if getattr(exc, "status_code", None) in (400, 401, 403, 404, 422):
                        break
                    if attempt < self.max_retries:
                        time.sleep(self._retry_delay(exc, attempt))
                    else:
                        break

        raise LLMError("所有已配置的 LLM 厂商均调用失败", failures)

    def _retry_delay(self, exc: Exception, attempt: int) -> float:
        """429 限流优先按响应头 Retry-After 等待（封顶 30s），否则指数退避。"""
        if getattr(exc, "status_code", None) == 429:
            headers = getattr(getattr(exc, "response", None), "headers", None)
            retry_after = headers.get("retry-after") if headers else None
            try:
                if retry_after is not None:
                    return min(float(retry_after), 30.0)
            except (TypeError, ValueError):
                pass
        return self.retry_base_seconds * (2**attempt)

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
    ) -> tuple[str, bool]:
        """调用厂商 SDK，返回 (文本, 是否因 max_tokens 截断)。"""
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
    ) -> tuple[str, bool]:
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
        }
        model_lower = provider.model.lower()
        if model_lower.startswith(("o1", "o3", "o4")) or "reasoning" in model_lower:
            # reasoning 模型不收 temperature，且以 max_completion_tokens 计量
            request["max_completion_tokens"] = options["max_tokens"]
        else:
            request["temperature"] = options["temperature"]
            request["max_tokens"] = options["max_tokens"]
        if options.get("json_mode"):
            request["response_format"] = {"type": "json_object"}

        client = _get_sdk_client(("openai", provider.api_key, provider.base_url), lambda: OpenAI(**kwargs))
        response = client.chat.completions.create(**request)
        choice = response.choices[0]
        return strip_model_noise(choice.message.content or ""), choice.finish_reason == "length"

    @staticmethod
    def _call_anthropic(
        provider: ProviderSettings,
        messages: Sequence[Message],
        options: dict[str, Any],
    ) -> tuple[str, bool]:
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
        if options.get("json_mode"):
            # Anthropic 无 response_format：system 约束 + assistant 预填 "{" 强制 JSON
            system_prompt = (system_prompt + "\n只输出一个 JSON 对象，不要输出其他内容").strip()
            user_messages.append({"role": "assistant", "content": "{"})

        kwargs: dict[str, Any] = {"api_key": provider.api_key, "timeout": options["timeout"]}
        if provider.base_url:
            kwargs["base_url"] = provider.base_url

        client = _get_sdk_client(("anthropic", provider.api_key, provider.base_url), lambda: Anthropic(**kwargs))
        response = client.messages.create(
            model=provider.model,
            system=system_prompt,
            messages=user_messages,
            temperature=options["temperature"],
            max_tokens=options["max_tokens"],
        )
        text = "\n".join(getattr(block, "text", "") for block in response.content)
        if options.get("json_mode"):
            text = "{" + text  # 拼回预填的开括号
        return strip_model_noise(text), response.stop_reason == "max_tokens"


def strip_model_noise(text: str) -> str:
    """移除常见模型思考标签（<think>/<thinking>，大小写不敏感）和外层空白。"""

    return re.sub(r"<think(?:ing)?>[\s\S]*?</think(?:ing)?>", "", text, flags=re.IGNORECASE).strip()


def parse_json_object(raw: str) -> Any:
    """从模型输出中解析 JSON，兼容代码块、前后解释文字和尾逗号。"""

    cleaned = strip_model_noise(raw).strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 逐个尝试全部平衡括号片段：模型可能先给 [引用] 之类的非 JSON 片段
    last_error: json.JSONDecodeError | None = None
    for candidate in _extract_balanced_json(cleaned):
        candidate = re.sub(r",(\s*[}\]])", r"\1", candidate)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    raise ValueError(f"无法从 LLM 返回中定位 JSON: {raw[:200]}")


def _extract_balanced_json(text: str):
    """产出文本中全部平衡括号片段（模型可能在解释文字之后再给 JSON）。"""
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
                    yield text[start : idx + 1]
                    break
