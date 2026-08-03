"""全局 LLM 配置管理。

厂商预设、.env 读写、「当前生效厂商」（LLM_ACTIVE_VENDOR）与统一的
LLMClient 构造入口。仿真、文档分析、画像生成、结果分析等所有 AI
调用点统一从这里取配置，不再各自拼装 ProviderSettings。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from config import DB_PATH, ROOT_DIR, app_config
from llm.client import LLMClient, LLMError, LLMProvider, ProviderSettings

PRESETS = [
    {"label": "Anthropic", "proto": "anthropic", "url": "https://api.anthropic.com", "model": "claude-fable-5"},
    {"label": "DeepSeek", "proto": "openai", "url": "https://api.deepseek.com", "model": "deepseek-v4-pro"},
    {"label": "Kimi", "proto": "openai", "url": "https://api.moonshot.cn/v1", "model": "kimi-k3"},
    {"label": "OpenAI", "proto": "openai", "url": "https://api.openai.com/v1", "model": "gpt-5.6-sol"},
    {"label": "通义千问", "proto": "openai", "url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen3.7-max"},
    {"label": "智谱", "proto": "openai", "url": "https://open.bigmodel.cn/api/paas/v4", "model": "glm-5.2"},
    {"label": "自定义", "proto": "openai", "url": "", "model": ""},
]

# 厂商索引 → .env 环境变量前缀
VENDOR_ENV_PREFIX = {
    0: "ANTHROPIC",
    1: "DEEPSEEK",
    2: "KIMI",
    3: "OPENAI",
    4: "QWEN",
    5: "ZHIPU",
    6: "CUSTOM",
}

# 当前生效厂商索引（.env 中的键名），Step1/2/4 的 AI 功能与仿真统一使用
ACTIVE_VENDOR_ENV = "LLM_ACTIVE_VENDOR"


def _env_path(env_path: str | Path | None = None) -> Path:
    if env_path:
        return Path(env_path)
    # 冻结（PyInstaller）后 ROOT_DIR 在 .app 包内通常只读，
    # 与数据库一样落到用户数据目录
    if getattr(sys, "frozen", False):
        return DB_PATH.parent / ".env"
    return ROOT_DIR / ".env"


def load_vendor_state() -> dict[int, dict[str, str]]:
    """从环境变量读取各厂商已保存的 key/url/model。"""
    state: dict[int, dict[str, str]] = {}
    for idx, prefix in VENDOR_ENV_PREFIX.items():
        key = os.getenv(f"{prefix}_API_KEY", "")
        url = os.getenv(f"{prefix}_BASE_URL", "")
        model = os.getenv(f"{prefix}_MODEL", "")
        preset = PRESETS[idx]
        if key or url or model:
            state[idx] = {
                "key": key,
                "url": url or preset.get("url", ""),
                "model": model or preset.get("model", ""),
            }
    return state


def get_active_vendor() -> int:
    """当前生效厂商索引，非法值回退 0。"""
    try:
        idx = int(os.getenv(ACTIVE_VENDOR_ENV, "0"))
    except ValueError:
        return 0
    return idx if idx in VENDOR_ENV_PREFIX else 0


def _persist_key(env_file: Path, name: str, value: str) -> bool:
    """写入 .env 并同步当前进程环境变量（同进程内立即生效）。

    返回 .env 是否写入成功；失败时进程内值仍生效，但重启后丢失，
    调用方应据此提示用户。
    """
    os.environ[name] = value
    try:
        from dotenv import set_key as dotenv_set_key
    except ImportError:
        return False
    try:
        dotenv_set_key(str(env_file), name, value)
        return True
    except Exception:
        return False


def persist_env_vars(
    mapping: dict[str, str],
    env_path: str | Path | None = None,
) -> bool:
    """持久化任意环境变量键值到 .env（并同步当前进程）。返回是否全部写入成功。"""
    env_file = _env_path(env_path)
    return all(_persist_key(env_file, name, value) for name, value in mapping.items())


def persist_vendor_state(
    state: dict[int, dict[str, str]],
    active_vendor: int | None = None,
    env_path: str | Path | None = None,
) -> bool:
    """把全部厂商配置（及生效厂商）持久化到 .env。返回是否全部写入成功。"""
    env_file = _env_path(env_path)
    ok = True
    for idx, vendor in state.items():
        if idx not in VENDOR_ENV_PREFIX:
            continue
        prefix = VENDOR_ENV_PREFIX[idx]
        for field, suffix in [("key", "API_KEY"), ("url", "BASE_URL"), ("model", "MODEL")]:
            ok = _persist_key(env_file, f"{prefix}_{suffix}", vendor.get(field, "")) and ok
    if active_vendor is not None:
        ok = _persist_key(env_file, ACTIVE_VENDOR_ENV, str(active_vendor)) and ok
    return ok


def get_active_provider_settings(
    state: dict[int, dict[str, str]] | None = None,
) -> ProviderSettings | None:
    """当前生效厂商的 ProviderSettings；未配置 API Key 时返回 None。"""
    if state is None:
        state = load_vendor_state()
    idx = get_active_vendor()
    preset = PRESETS[idx]
    prefix = VENDOR_ENV_PREFIX[idx]
    vendor = state.get(idx, {})
    key = vendor.get("key") or os.getenv(f"{prefix}_API_KEY") or ""
    if not key:
        return None
    provider = (
        LLMProvider.ANTHROPIC
        if preset.get("proto") == "anthropic"
        else LLMProvider.OPENAI
    )
    return ProviderSettings(
        provider,
        vendor.get("model") or preset.get("model", ""),
        key,
        vendor.get("url") or preset.get("url", "") or None,
    )


def build_llm_client(max_retries: int | None = None) -> LLMClient | None:
    """按当前生效厂商构造 LLMClient。

    生效厂商无 Key 时回退 from_env() 的 OPENAI/ANTHROPIC 环境变量链；
    均不可用返回 None（调用方据此禁用 AI 功能或提示去设置页）。
    """
    retries = app_config.llm.max_retries if max_retries is None else max_retries
    settings = get_active_provider_settings()
    if settings is not None:
        return LLMClient(providers=[settings], max_retries=retries)
    try:
        return LLMClient.from_env()
    except LLMError:
        return None


def active_vendor_label() -> str:
    """供 UI 展示的当前配置摘要，如「Kimi · kimi-k3」。"""
    idx = get_active_vendor()
    preset = PRESETS[idx]
    settings = get_active_provider_settings()
    if settings is None:
        return f"{preset['label']}（未配置 API Key）"
    return f"{preset['label']} · {settings.model}"


def check_provider(settings: ProviderSettings) -> str:
    """用指定配置发一条最小请求验证连通性，失败抛异常。"""
    client = LLMClient(providers=[settings], max_retries=0)
    return client.chat("你是连通性测试助手。", "ping")
