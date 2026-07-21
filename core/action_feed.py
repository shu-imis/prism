"""行动信息流 —— 行为体行动的共享记录与个性化观察层。

借鉴 MiroFish/OASIS 的环境中心化互动模型：行为体之间不直接通信，
每轮行动写入共享信息流；下一轮各行为体从信息流中获取与自己相关的
观察（供应链邻居的行动 + 全链高影响力行动），反应链因此跨轮形成。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

_METRIC_LABELS = {
    "inventory_change": "库存",
    "cost_change": "成本",
    "delay_change": "延迟",
    "service_change": "服务",
    "margin_change": "利润",
}


@dataclass
class ActionRecord:
    """单个行为体在一轮中的结构化行动。"""

    round: int
    agent_id: int
    agent_name: str
    role: str
    action_type: str
    content: str                              # 行动原话摘要
    metrics: dict[str, float] = field(default_factory=dict)
    influence: float = 1.0
    reaction_to: str = "none"                 # 回应对象行为体名，"none" 表示自主决策

    def format_entry(self, relation: str = "") -> str:
        """格式化为观察层条目，relation 为相对链路方位（上游/下游/全链广播）。"""
        # 种子事件等环境干预不是行为体，显式标注防止模型将其当作回应对象
        if self.action_type == "seed":
            return f"- {self.agent_name}（{self.role}）｜「{self.content}」（环境事件，不可作为回应对象）"
        rel = f"{relation}·" if relation else ""
        deltas = " ".join(
            f"{_METRIC_LABELS.get(key, key)}{value:+g}"
            for key, value in self.metrics.items()
            if value
        )
        reaction = f"回应@{self.reaction_to} " if self.reaction_to != "none" else ""
        return f"- {self.agent_name}（{rel}{self.role}）【{self.action_type}】{reaction}{deltas} ｜「{self.content}」"


class ActionFeed:
    """单次仿真内的共享行动信息流（纯内存，随仿真结束销毁）。

    可见性规则与 MiroFish 的推荐层对应：邻居行动全部可见，
    非邻居行动仅当其影响力达到广播阈值时可见。
    """

    def __init__(self, broadcast_influence: float = 1.5, max_rounds_kept: int = 2):
        self._records: list[ActionRecord] = []
        self.broadcast_influence = broadcast_influence
        self.max_rounds_kept = max_rounds_kept

    def append(self, records: Iterable[ActionRecord]) -> None:
        self._records.extend(records)

    @property
    def current_round(self) -> int:
        return self._records[-1].round if self._records else 0

    def last_entry_for(self, agent_id: int) -> ActionRecord | None:
        """某行为体自己最近一条行动记录（用于在 prompt 中回显其上轮发言）。"""
        for record in reversed(self._records):
            if record.agent_id == agent_id:
                return record
        return None

    def for_agent(self, agent_id: int, neighbor_ids: set[int], limit: int = 6) -> list[ActionRecord]:
        """返回某行为体的个性化观察，按轮次正序排列。

        只取最近 max_rounds_kept 轮；自身行动不进入观察；
        同一行为体同一轮只保留一条。
        """
        if not self._records:
            return []
        min_round = self.current_round - self.max_rounds_kept + 1
        seen: set[tuple[int, int]] = set()
        picked: list[ActionRecord] = []
        for record in reversed(self._records):
            if record.round < min_round:
                break
            if record.agent_id == agent_id:
                continue
            if record.agent_id not in neighbor_ids and record.influence < self.broadcast_influence:
                continue
            key = (record.round, record.agent_id)
            if key in seen:
                continue
            seen.add(key)
            picked.append(record)
            if len(picked) >= limit:
                break
        picked.reverse()
        return picked
