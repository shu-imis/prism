# 预留功能与待实现模块

本文档记录已预留接口但尚未接入主流程的功能模块，避免未来开发者误删。

---

## 1. 图表模块（`report/charts.py`）

**状态**：接口已定义，实现待接入 pyqtgraph。

| 类 | 用途 | 待实现 |
|---|---|---|
| `PrismChart` | 图表基类 | 接入 pyqtgraph 渲染 |
| `SupplyChainCurveChart` | 库存/成本/交付延迟双方案叠加曲线图 | 接入仿真数据，绑定 UI |
| `RadarChart` | 六维方案评估雷达图 | 接入评分数据，绑定 UI |

**负责人**：csf（可视化 & QA 工程师）

**接入时机**：仿真结果页（`ui/result_page.py`）完成基础表格后。

---

## 2. LLM 策略评估 Prompt（`llm/prompts.py`）

**状态**：Prompt 模板已定义，尚未接入引擎。

| Prompt | 用途 |
|---|---|
| `STRATEGY_EVALUATION_SYSTEM` | LLM 驱动的六维方案评分 + 风险分析 |
| `REPORT_GENERATION_SYSTEM` | LLM 驱动的 Markdown 报告生成 |

**当前替代方案**：`report/generator.py` 使用程序化公式计算评分。

**接入时机**：当需要更深度、可解释的评估时，替换或补充程序化评分。

---

## 3. AgentFactory 辅助方法（`core/agent_factory.py`）

| 方法 | 用途 | 使用场景 |
|---|---|---|
| `create_by_ids(agent_ids)` | 按需创建指定行为体子集 | 仅仿真特定环节的行为体 |
| `get_template(agent_id)` | 获取单个行为体模板 | UI 展示行为体详情、动态修改模板 |

---

## 4. 加权平均工具（`core/simulation_engine.py`）

`_weighted_average(values, fallback)` — 通用加权平均函数，预留用于供应链指标聚合公式。

---

## 变更记录

| 日期 | 变更 |
|------|------|
| 2026-07-15 | 从舆情推演改造为供应链决策推演，清理死代码，保留上述预留功能 |
