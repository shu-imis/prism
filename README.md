# Prism

**棱镜折射 · 透视供应链连锁反应**

面向供应链管理者的桌面端决策推演工具。供应链中某一节点的决策如同一束光，经上下游折射产生截然不同的全局影响 — Prism 让你在实际执行前，透视每一种方案对整个供应链的连锁反应，获取数据化的决策建议。

## 快速开始

```bash
pip install -r requirements.txt
cp .env.example .env    # 编辑 .env，填入 LLM API Key
python main.py
```

## 技术栈

- **UI**: PySide6
- **LLM**: OpenAI / Anthropic SDK（双厂商 fallback）
- **数据**: SQLite（WAL 模式）
- **报告**: WeasyPrint（PDF）+ 应用内预览
- **文档解析**: pypdf + python-docx（RAG 文档导入）
- **配置**: python-dotenv

## 项目结构

```
prism/
├── main.py
├── config.py
├── assets/fonts/              # 内嵌字体（Space Grotesk / JetBrains Mono / Noto Sans SC）
├── ui/
│   ├── main_window.py         # 主窗口 + 侧边栏导航
│   ├── home_page.py           # 首页 — 项目列表
│   ├── process_page.py        # 工作区 — 4 步流程（搭建→决策→仿真→结果）
│   ├── event_page.py          # 供应链搭建（Step 01）
│   ├── strategy_page.py       # 行为体决策配置（Step 02）
│   ├── simulation_page.py     # 仿真运行（Step 03）
│   ├── result_page.py         # 结果分析（Step 04）
│   ├── widgets.py
│   └── styles.py              # 设计系统（Sigma 亮色主题）
├── core/
│   ├── agent.py               # 行为体数据类 + 模板
│   ├── agent_factory.py
│   ├── document_importer.py   # RAG 文档导入
│   ├── scenario_parser.py
│   ├── simulation_engine.py   # 多行为体仿真引擎
│   ├── world_state.py         # 供应链全局状态
│   └── events.py
├── llm/
│   ├── client.py              # 多厂商 LLM 客户端
│   └── prompts.py
├── report/
│   ├── generator.py
│   ├── charts.py
│   └── exporter.py
├── db/
│   ├── database.py
│   └── models.py
└── docs/
    └── prism.md               # 项目文档
```

## 许可

内部项目。
