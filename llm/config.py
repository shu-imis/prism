"""全局 LLM 配置管理。

厂商预设、.env 读写、「当前生效厂商」（LLM_ACTIVE_VENDOR）与统一的
LLMClient 构造入口。仿真、文档分析、画像生成、结果分析等所有 AI
调用点统一从这里取配置，不再各自拼装 ProviderSettings。

API Key 属于敏感信息，任何情况下都不明文落盘：
1. 优先存入操作系统钥匙串（macOS Keychain / Windows Credential
   Manager，经 keyring 库）；
2. 无可用钥匙串后端时（CI/无桌面环境），用本机特征（IOPlatformUUID /
   MachineGuid / machine-id）派生密钥做 Fernet 加密后写 .env
   （enc:v1: 前缀）——属本机绑定加密，安全级别低于钥匙串，但非明文；
3. 连本机特征也取不到时仅在进程内存中生效，不落盘。

启动时若发现 .env 中残留旧格式 Key（明文或 enc:v1: 密文）且钥匙串
可用，会自动迁移进钥匙串并清空 .env。
"""
from __future__ import annotations

import base64
import hashlib
import os
import re
import subprocess
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

# 钥匙串服务名（keyring 的 service 维度，username 用环境变量名如 KIMI_API_KEY）
_KEYRING_SERVICE = "Prism"


def _get_keyring():
    """返回可用的 keyring 模块；未安装或无可用后端（CI/无桌面环境）返回 None。"""
    try:
        import keyring
        from keyring.backends.fail import Keyring as FailKeyring
    except ImportError:
        return None
    try:
        backend = keyring.get_keyring()
    except Exception:
        return None
    return None if isinstance(backend, FailKeyring) else keyring


def _env_path(env_path: str | Path | None = None) -> Path:
    if env_path:
        return Path(env_path)
    # 冻结（PyInstaller）后 ROOT_DIR 在 .app 包内通常只读，
    # 与数据库一样落到用户数据目录
    if getattr(sys, "frozen", False):
        return DB_PATH.parent / ".env"
    return ROOT_DIR / ".env"


def _persist_key(
    env_file: Path,
    name: str,
    value: str,
    file_value: str | None = None,
) -> bool:
    """写入 .env 并同步当前进程环境变量（同进程内立即生效）。

    file_value 与 value 不同时（如密钥加密落盘），文件写 file_value、
    进程环境变量保留 value。返回 .env 是否写入成功；失败时进程内值
    仍生效，但重启后丢失，调用方应据此提示用户。
    """
    os.environ[name] = value
    try:
        from dotenv import set_key as dotenv_set_key
    except ImportError:
        return False
    try:
        dotenv_set_key(str(env_file), name, value if file_value is None else file_value)
        return True
    except Exception:
        return False


# --- 无钥匙串时的本机绑定加密兜底（Fernet，密钥由机器特征派生） ---
_ENC_PREFIX = "enc:v1:"
_ENC_SALT = b"prism-llm-secret-v1"


def _machine_secret() -> bytes | None:
    """本机特征值，用于派生兜底加密密钥；取不到返回 None（不落盘）。"""
    try:
        if sys.platform == "darwin":
            out = subprocess.run(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                capture_output=True, text=True, timeout=5,
            ).stdout
            m = re.search(r'"IOPlatformUUID"\s*=\s*"([^"]+)"', out)
            if m:
                return m.group(1).encode()
        elif sys.platform == "win32":
            import winreg
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography"
            ) as reg:
                return str(winreg.QueryValueEx(reg, "MachineGuid")[0]).encode()
        else:
            for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
                try:
                    machine_id = Path(path).read_text(encoding="utf-8").strip()
                except OSError:
                    continue
                if machine_id:
                    return machine_id.encode()
    except Exception:
        pass
    return None


def _fernet():
    """由本机特征派生 Fernet 实例；特征或 cryptography 不可用返回 None。"""
    secret = _machine_secret()
    if secret is None:
        return None
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        return None
    digest = hashlib.pbkdf2_hmac("sha256", secret, _ENC_SALT, 100_000, dklen=32)
    return Fernet(base64.urlsafe_b64encode(digest))


def _encrypt_value(plaintext: str) -> str | None:
    """加密为带 enc:v1: 前缀的密文；无法派生密钥时返回 None。"""
    f = _fernet()
    if f is None:
        return None
    return _ENC_PREFIX + f.encrypt(plaintext.encode("utf-8")).decode("ascii")


def _decrypt_value(value: str) -> str:
    """enc:v1: 密文解密；非密文原样返回，解密失败返回空串。"""
    if not value.startswith(_ENC_PREFIX):
        return value
    f = _fernet()
    if f is None:
        return ""
    try:
        return f.decrypt(value[len(_ENC_PREFIX):].encode("ascii")).decode("utf-8")
    except Exception:
        return ""


def _persist_encrypted(env_file: Path, name: str, value: str) -> bool:
    """无钥匙串时的兜底：Fernet 加密后写 .env（进程内仍保留明文立即可用）。

    无法派生密钥时只在进程内存生效、不落盘，返回 False 让调用方提示用户。
    """
    if not value:
        return _persist_key(env_file, name, "")
    encrypted = _encrypt_value(value)
    if encrypted is None:
        os.environ[name] = value
        return False
    return _persist_key(env_file, name, value, file_value=encrypted)


def _get_secret(name: str) -> str:
    """读取密钥：优先系统钥匙串，回退 .env/环境变量（自动解密 enc:v1: 密文）。"""
    kr = _get_keyring()
    if kr is not None:
        try:
            value = kr.get_password(_KEYRING_SERVICE, name)
        except Exception:
            value = None
        if value:
            return value
    return _decrypt_value(os.getenv(name, ""))


def _set_secret(env_file: Path, name: str, value: str) -> bool:
    """写入密钥到系统钥匙串，并清除 .env / 环境变量中的残留（明文或密文）。

    无可用钥匙串后端（或钥匙串写失败）时回退本机绑定加密写 .env，
    任何路径都不落盘明文。返回是否持久化成功。
    """
    kr = _get_keyring()
    if kr is None:
        return _persist_encrypted(env_file, name, value)
    try:
        if value:
            kr.set_password(_KEYRING_SERVICE, name, value)
        else:
            try:
                kr.delete_password(_KEYRING_SERVICE, name)
            except Exception:
                pass  # 条目本就不存在
    except Exception:
        # 钥匙串写入异常时回退加密 .env，保证配置不丢
        return _persist_encrypted(env_file, name, value)
    # 已进钥匙串：清空 .env 与进程环境变量中的残留（明文或密文）
    return _persist_key(env_file, name, "")


def _migrate_secret_to_keyring(env_file: Path, name: str) -> None:
    """一次性迁移：.env/环境变量里的 Key（明文或 enc:v1: 密文）搬进钥匙串。"""
    kr = _get_keyring()
    if kr is None:
        return
    plaintext = _decrypt_value(os.getenv(name, ""))
    if not plaintext:
        return
    try:
        if kr.get_password(_KEYRING_SERVICE, name):
            return  # 钥匙串已有值，以钥匙串为准
    except Exception:
        return
    _set_secret(env_file, name, plaintext)


def load_vendor_state() -> dict[int, dict[str, str]]:
    """读取各厂商已保存的 key/url/model（key 优先取钥匙串，旧格式自动迁移）。"""
    env_file = _env_path()
    state: dict[int, dict[str, str]] = {}
    for idx, prefix in VENDOR_ENV_PREFIX.items():
        key_name = f"{prefix}_API_KEY"
        _migrate_secret_to_keyring(env_file, key_name)
        key = _get_secret(key_name)
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
    """把全部厂商配置（及生效厂商）持久化：key 入钥匙串，url/model/厂商入 .env。"""
    env_file = _env_path(env_path)
    ok = True
    for idx, vendor in state.items():
        if idx not in VENDOR_ENV_PREFIX:
            continue
        prefix = VENDOR_ENV_PREFIX[idx]
        ok = _set_secret(env_file, f"{prefix}_API_KEY", vendor.get("key", "")) and ok
        for field, suffix in [("url", "BASE_URL"), ("model", "MODEL")]:
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
    key = vendor.get("key") or _get_secret(f"{prefix}_API_KEY") or ""
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

    生效厂商无 Key 时回退 from_env() 的 OPENAI/ANTHROPIC 链（含钥匙串）；
    均不可用返回 None（调用方据此禁用 AI 功能或提示去设置页）。
    """
    retries = app_config.llm.max_retries if max_retries is None else max_retries
    settings = get_active_provider_settings()
    if settings is not None:
        return LLMClient(providers=[settings], max_retries=retries)
    try:
        return LLMClient.from_env(
            openai_key=_get_secret("OPENAI_API_KEY") or None,
            anthropic_key=_get_secret("ANTHROPIC_API_KEY") or None,
        )
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
