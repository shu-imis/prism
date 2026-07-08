"""多厂商 LLM 客户端

封装 OpenAI 和 Anthropic SDK，支持：
  - 厂商 fallback（任一不可用时自动切换）
  - 指数退避重试（最多 3 次）
  - JSON 模式输出 + 格式修复
  - 超时控制（默认 30s）

参考 MiroFish LLMClient 的设计模式。
"""
from __future__ import annotations

import json
import time
import re
from enum import Enum
from typing import Optional, Any

from prism.config import app_config


class LLMProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


class LLMClient:
    """多厂商 LLM 客户端"""

    def __init__(
        self,
        provider: LLMProvider = LLMProvider.OPENAI,
        model: str | None = None,
        api_key: str | None = None,
        temperature: float | None = None,
        max_retries: int | None = None,
        timeout: int | None = None,
    ):
        self.provider = provider
        self.model = model or app_config.llm.default_model
        self.api_key = api_key
        self.temperature = temperature or app_config.llm.temperature
        self.max_retries = max_retries or app_config.llm.max_retries
        self.timeout = timeout or app_config.llm.request_timeout
        self._client: Any = None

    def _get_client(self):
        """延迟初始化客户端"""
        if self._client is not None:
            return self._client

        if self.provider == LLMProvider.OPENAI:
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=self.api_key, timeout=self.timeout)
            except ImportError:
                raise ImportError("openai 包未安装。运行: pip install openai")
        elif self.provider == LLMProvider.ANTHROPIC:
            try:
                from anthropic import Anthropic
                self._client = Anthropic(api_key=self.api_key, timeout=self.timeout)
            except ImportError:
                raise ImportError("anthropic 包未安装。运行: pip install anthropic")

        return self._client

    def chat(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float | None = None,
    ) -> str:
        """发送对话请求，返回纯文本"""
        client = self._get_client()
        temp = temperature or self.temperature

        for attempt in range(self.max_retries):
            try:
                if self.provider == LLMProvider.OPENAI:
                    response = client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_message},
                        ],
                        temperature=temp,
                    )
                    return response.choices[0].message.content or ""

                elif self.provider == LLMProvider.ANTHROPIC:
                    response = client.messages.create(
                        model=self.model,
                        system=system_prompt,
                        messages=[{"role": "user", "content": user_message}],
                        temperature=temp,
                        max_tokens=4096,
                    )
                    return response.content[0].text or ""

            except Exception as e:
                if attempt < self.max_retries - 1:
                    wait = 2 ** attempt
                    time.sleep(wait)
                else:
                    raise RuntimeError(f"LLM 调用失败（已重试 {self.max_retries} 次）: {e}")

        return ""

    def chat_json(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float | None = None,
    ) -> dict:
        """发送对话请求，返回解析后的 JSON dict"""
        raw = self.chat(system_prompt, user_message, temperature)
        return self._parse_json(raw)

    @staticmethod
    def _parse_json(raw: str) -> dict:
        """解析 LLM 返回的 JSON，尝试修复常见格式错误"""
        # 去除 markdown 代码块包裹
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            # 尝试修复：截取第一个完整 JSON 对象
            brace_count = 0
            end_idx = -1
            for i, ch in enumerate(cleaned):
                if ch == "{":
                    brace_count += 1
                elif ch == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        end_idx = i + 1
                        break
            if end_idx > 0:
                try:
                    return json.loads(cleaned[:end_idx])
                except json.JSONDecodeError:
                    pass
            raise ValueError(f"无法解析 LLM 返回的 JSON: {raw[:200]}...")


class LLMClientFactory:
    """LLM 客户端工厂 —— 检测可用厂商并创建客户端"""

    @staticmethod
    def create(
        prefer: LLMProvider = LLMProvider.OPENAI,
        openai_key: str | None = None,
        anthropic_key: str | None = None,
    ) -> LLMClient:
        """创建客户端，优先使用指定厂商，不可用时 fallback"""
        import os

        oai_key = openai_key or os.getenv("OPENAI_API_KEY")
        ant_key = anthropic_key or os.getenv("ANTHROPIC_API_KEY")

        if prefer == LLMProvider.OPENAI and oai_key:
            return LLMClient(provider=LLMProvider.OPENAI, api_key=oai_key)
        if prefer == LLMProvider.ANTHROPIC and ant_key:
            return LLMClient(provider=LLMProvider.ANTHROPIC, api_key=ant_key)

        # fallback
        if oai_key:
            return LLMClient(provider=LLMProvider.OPENAI, api_key=oai_key)
        if ant_key:
            return LLMClient(provider=LLMProvider.ANTHROPIC, api_key=ant_key)

        raise RuntimeError(
            "未找到可用的 LLM API Key。请在 .env 中设置 OPENAI_API_KEY 或 ANTHROPIC_API_KEY。"
        )
