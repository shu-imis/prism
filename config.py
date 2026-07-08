"""全局配置模块

集中管理所有可调参数，避免硬编码分散。
参考 MiroFish Config 模式：从环境变量加载，提供类方法验证。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# ============================================================
# 路径常量
# ============================================================
ROOT_DIR = Path(__file__).parent
ASSETS_DIR = ROOT_DIR / "assets"
DB_PATH = ROOT_DIR / "prism.db"


# ============================================================
# 仿真默认配置
# ============================================================
@dataclass
class SimulationDefaults:
    """仿真引擎默认参数"""
    max_rounds: int = 12
    hours_per_round: int = 4
    agent_count: int = 8
    min_strategies: int = 2
    max_strategies: int = 4
    round_timeout: int = 120  # 单轮最大耗时（秒）
    checkpoint_interval: int = 1  # 每 N 轮保存检查点


@dataclass
class LLMDefaults:
    """LLM 调用默认参数"""
    default_model: str = "gpt-4o-mini"
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
            hours_per_round=int(os.getenv("SIM_HOURS_PER_ROUND", "4")),
            agent_count=int(os.getenv("SIM_AGENT_COUNT", "8")),
        )
        llm = LLMDefaults(
            default_model=os.getenv("LLM_DEFAULT_MODEL", "gpt-4o-mini"),
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.7")),
            max_retries=int(os.getenv("LLM_MAX_RETRIES", "3")),
            request_timeout=int(os.getenv("LLM_REQUEST_TIMEOUT", "30")),
        )
        return cls(sim=sim, llm=llm)


# 全局配置实例
app_config = AppConfig.from_env()
