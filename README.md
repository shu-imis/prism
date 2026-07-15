# Prism

**棱镜折射 · 透视供应链连锁反应**

面向供应链管理者的桌面端决策推演工具。构建供应链网络，配置决策方案，通过 7 类行为体的 LLM 仿真，观察不同方案对整条供应链的连锁影响——在真实执行前，获取数据化的决策建议。

## 工作流

```
供应链搭建 → 行为体决策配置 → 多行为体仿真 → 结果分析 → 导出报告
```

1. **供应链搭建** — 定义行业、节点、初始库存/成本/服务水平，导入背景文档
2. **行为体决策配置** — 2~4 组对比方案，指定行为体、决策内容与生效周期
3. **多行为体仿真** — 7 类行为体（供应商→制造商→分销商→零售商→物流→消费者→监管）LLM 推演，实时显示库存/成本/服务水平/利润率/交付延迟
4. **结果分析** — 方案对比表、六维评分雷达图、风险提示，一键导出 Markdown/PDF

## 核心特性

- **多行为体 LLM 仿真**：每个行为体由独立 LLM prompt 驱动，根据全局状态自主决策
- **关键事件系统**：6 种供应链事件（断供、爆仓、价格战、监管介入、需求激增、自然恢复）动态触发
- **方案对比**：双方案并行推演，六维度评分（成本控制/交付稳定性/库存健康度/风险抵御/协同效率/可执行性）
- **检查点恢复**：每轮自动持久化，中断后可无缝继续
- **RAG 知识检索**：导入 PDF/Word/Markdown 文档，仿真中自动检索相关背景

## 快速开始

```bash
pip install -r requirements.txt
cp .env.example .env    # 编辑 .env，填入 LLM API Key
python main.py
```

## 技术栈

| 用途 | 技术 |
|------|------|
| 桌面 UI | PySide6 |
| LLM 调用 | OpenAI / Anthropic SDK（双厂商 fallback） |
| 数据存储 | SQLite（WAL 模式） |
| 报告导出 | WeasyPrint（PDF）+ Markdown |
| 文档解析 | pypdf + python-docx |
| 配置管理 | python-dotenv |

## 项目结构

```
prism/
├── main.py
├── config.py
├── ui/                          # PySide6 界面
│   ├── main_window.py
│   ├── home_page.py
│   ├── process_page.py          # 4 步工作流协调
│   ├── event_page.py            # 供应链搭建（Step 01）
│   ├── strategy_page.py         # 行为体决策配置（Step 02）
│   ├── simulation_page.py       # 仿真运行（Step 03）
│   ├── result_page.py           # 结果分析（Step 04）
│   ├── widgets.py
│   └── styles.py
├── core/                        # 仿真引擎 + 行为体 + 事件
│   ├── agent.py
│   ├── agent_factory.py
│   ├── document_importer.py
│   ├── scenario_parser.py
│   ├── simulation_engine.py
│   ├── world_state.py
│   └── events.py
├── llm/                         # LLM 客户端 + Prompt
│   ├── client.py
│   └── prompts.py
├── report/                      # 报告生成 + 导出 + 图表
│   ├── generator.py
│   ├── charts.py
│   └── exporter.py
├── db/                          # SQLite 数据访问
│   ├── database.py
│   └── models.py
├── tests/
│   └── test_backend_modules.py
└── docs/
    ├── prism.md                 # 完整项目文档
    └── roadmap.md               # 路线图
```

## 文档

- [项目文档](docs/prism.md) — 完整的产品定义、设计系统、仿真模型
- [路线图](docs/roadmap.md) — 版本规划与待实现功能

## 许可

内部项目。
