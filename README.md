# Prism

**棱镜折射 · 预见舆论光谱**

面向企业公关与品牌团队的桌面端危机公关推演工具。同一事件经由不同公众视角折射，呈现截然不同的舆论光谱 — Prism 让你在正式发声前，透视每一种策略可能引发的舆论走向。

## 技术栈

- **UI**: PySide6
- **LLM**: OpenAI / Anthropic SDK（双厂商 fallback）
- **数据**: SQLite（WAL 模式）
- **图表**: pyqtgraph
- **报告**: WeasyPrint（PDF）+ QTextBrowser（预览）
- **配置**: python-dotenv + keyring

## 快速开始

```bash
# 1. 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 LLM API Key

# 4. 启动应用
python main.py
```

## 项目结构

```
prism/
├── main.py                  # 应用入口
├── config.py                # 全局配置
├── requirements.txt
├── .env.example
├── .gitignore
├── ui/                      # 界面层
│   ├── main_window.py       # 主窗口 + 页面路由
│   ├── styles.py            # 设计系统（色彩 + QSS）
│   ├── widgets.py           # 可复用组件
│   ├── logo.py                # 棱镜折射图形（QPainter）
│   ├── welcome_page.py      # 首页
│   ├── project_list_page.py # 历史项目
│   ├── event_page.py        # 事件录入
│   ├── strategy_page.py     # 策略配置
│   ├── simulation_page.py   # 仿真运行
│   └── result_page.py       # 结果分析
├── core/                    # 核心层
│   ├── agent.py             # Agent 数据模型 + 8 类模板
│   ├── agent_factory.py     # Agent 工厂
│   ├── world_state.py       # WorldState 数据模型
│   ├── events.py            # 关键事件定义 + 检测
│   ├── scenario_parser.py   # 场景解析器
│   └── simulation_engine.py # 仿真引擎
├── llm/                     # LLM 层
│   ├── client.py            # 多厂商 LLM 客户端
│   └── prompts.py           # Prompt 模板
├── report/                  # 报告层
│   ├── generator.py          # 报告生成器
│   ├── charts.py            # 图表封装
│   └── exporter.py          # PDF 导出
├── db/                      # 数据层
│   ├── database.py          # SQLite 连接管理
│   └── models.py            # ORM 模型
├── assets/                  # 静态资源
│   └── icons/
└── docs/
    └── prism.md             # 项目规划文档
```

## 后端模块交付

后端能力直接维护在 `llm/`、`db/`、`report/` 三个既有目录中，覆盖 LLM 多厂商封装、SQLite 持久化和报告生成 / 导出。使用方式与 PR 说明见 [docs/backend_module.md](docs/backend_module.md)。

## 开发计划

详见 [docs/prism.md](docs/prism.md)。

## 许可

内部项目。
