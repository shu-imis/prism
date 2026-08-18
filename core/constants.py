"""领域词汇单一来源 —— 指标、行动类型、节点类型的规范化词典。

各渲染层（prompt / Markdown 表格 / 图表 / 观察层）统一从这里取词表，
避免同一概念在多处各写一份导致措辞漂移。
"""
from typing import Final

# 5 项核心指标（规范顺序：库存、成本、交付延迟、服务水平、利润率）
# key 为抽象概念名；各渲染层的字段映射（inventory_level / cost_index …）保留在各层
METRICS: Final[dict[str, str]] = {
    "inventory": "库存",
    "cost": "成本",
    "delay": "交付延迟",
    "service": "服务水平",
    "margin": "利润率",
}

# 8 种行动类型（key → 长说明）。
# 顺序与 AGENT_RESPONSE_SYSTEM 的 action_type 枚举保持一致（该枚举由此字典渲染）。
ACTION_TYPES: Final[dict[str, str]] = {
    "maintain": "维持现状",
    "adjust_supply": "调整供应/采购量",
    "adjust_price": "调价/促销",
    "adjust_capacity": "产能/库存策略调整",
    "expedite_logistics": "物流加急/改道",
    "reduce_orders": "削减订单",
    "shift_demand": "需求转移/抵制",
    "intervene": "监管介入",
}

# 行动类型 → 泳道图短标签
ACTION_LABELS_SHORT: Final[dict[str, str]] = {
    "maintain": "维持",
    "adjust_supply": "调供应",
    "adjust_price": "调价",
    "adjust_capacity": "调产能",
    "expedite_logistics": "物流加急",
    "reduce_orders": "减订单",
    "shift_demand": "需求转移",
    "intervene": "监管介入",
}

# 7 种供应链节点类型（key → 中文标签），列表顺序即行为体 id 顺序（1..7）
NODE_TYPES: Final[list[tuple[str, str]]] = [
    ("supplier", "原材料供应商"),
    ("manufacturer", "制造商"),
    ("distributor", "分销商"),
    ("retailer", "零售商"),
    ("logistics", "物流服务商"),
    ("consumer", "消费者"),
    ("regulator", "监管机构"),
]