"""全局配置模块

集中管理所有可调参数，避免硬编码分散。
支持从环境变量加载（.env 兜底）。
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ============================================================
# 路径常量
# ============================================================
ROOT_DIR = Path(__file__).parent


def _default_db_path() -> Path:
    """数据库文件位置。

    开发时放在项目根目录；PyInstaller 冻结后改用各平台用户数据目录，
    避免写入 .app 包内 / 安装目录（可能只读，且升级时会被覆盖）。
    """
    if not getattr(sys, "frozen", False):
        return ROOT_DIR / "prism.db"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Prism" / "prism.db"
    if sys.platform == "win32":
        appdata = os.getenv("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        return base / "Prism" / "prism.db"
    return Path.home() / ".local" / "share" / "Prism" / "prism.db"


DB_PATH = _default_db_path()


# ============================================================
# 仿真默认配置
# ============================================================
@dataclass
class SimulationDefaults:
    """仿真引擎默认参数"""
    max_rounds: int = 12
    round_timeout: int = 120     # 单轮最大耗时（秒）


@dataclass
class LLMDefaults:
    """LLM 调用默认参数"""
    default_model: str = "gpt-5.6-sol"
    temperature: float = 0.7
    max_retries: int = 3
    request_timeout: int = 30


@dataclass
class AppConfig:
    """应用全局配置"""
    sim: SimulationDefaults = field(default_factory=SimulationDefaults)
    llm: LLMDefaults = field(default_factory=LLMDefaults)

    @classmethod
    def from_env(cls) -> AppConfig:
        """从环境变量加载配置（.env 兜底）"""
        sim = SimulationDefaults(
            max_rounds=int(os.getenv("SIM_MAX_ROUNDS", "12")),
        )
        llm = LLMDefaults(
            default_model=os.getenv("LLM_DEFAULT_MODEL", "gpt-5.6-sol"),
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.7")),
            max_retries=int(os.getenv("LLM_MAX_RETRIES", "3")),
            request_timeout=int(os.getenv("LLM_REQUEST_TIMEOUT", "30")),
        )
        return cls(sim=sim, llm=llm)


# 全局配置实例
app_config = AppConfig.from_env()
