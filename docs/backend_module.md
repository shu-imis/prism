# 后端模块交付说明

## 负责范围

本次后端交付不再新增个人命名包，而是直接补强项目既有结构：

- `llm/client.py`：多厂商 LLM 封装，支持 OpenAI-compatible 与 Anthropic，包含重试、fallback、JSON 模式和常见格式修复。
- `db/database.py`：SQLite 连接和迁移，包含项目、策略、轮次、Agent 发言、检查点、报告等表。
- `db/models.py`：轻量 Repository 数据访问层，覆盖项目、策略、轮次和报告 CRUD。
- `report/generator.py`：报告生成后端，基于仿真轮次计算六维评分、风险提示和推荐策略。
- `report/exporter.py`：Markdown / HTML / PDF 导出；WeasyPrint 不可用时自动降级为 HTML。
- `tests/test_backend_modules.py`：后端单元测试，覆盖数据库写读、LLM fallback、报告生成与导出。

## 本轮补救点

- 移除了个人首字母命名，避免在代码、表名、测试名和 PR 描述中暴露个人信息。
- 不再额外外挂后端包，避免 `llm/`、`db/`、`report/` 与新包重复分工。
- 将 `python main.py` 的导入方式修正为可从仓库目录直接运行，降低对本地文件夹名的依赖。
- 把原先的 TODO 型报告导出改为可用实现，PDF 依赖不可用时也会有 HTML 兜底产物。
- 为数据库 upsert、LLM fallback、报告输出补了测试，防止后续协作时回归。

## 项目仍需后续完善

- `core/simulation_engine.py` 仍是骨架，尚未真正调用 LLM 生成 Agent 反应并更新世界状态。
- UI 页面多为占位页，表单数据还没有完全接入数据库 Repository。
- 图表层 `report/charts.py` 仍是接口占位，需要接入 pyqtgraph 实际绘图。
- API Key 的 keyring 存储尚未落地，目前仍主要依赖环境变量。
- 打包、跨平台验证和 Demo 缓存数据还需要单独补充。

## 上传到 GitHub 的位置

在仓库根目录提交这些路径即可：

```text
llm/client.py
db/database.py
db/models.py
report/generator.py
report/exporter.py
tests/test_backend_modules.py
docs/backend_module.md
README.md
docs/prism.md
main.py
core/
ui/
```

参考项目只用于学习，不要上传 `_refs/`、本地 `.env`、`*.db`、`__pycache__/`。

## 本地验证

在仓库根目录执行：

```bash
python -m unittest tests.test_backend_modules
python -m compileall .
```

## PR 描述模板

标题建议：

```text
feat(backend): strengthen llm storage and reporting
```

正文建议：

```markdown
## 变更内容
- 补强现有后端模块：LLMClient、SQLite Repository、报告生成与导出
- 移除个人命名包，改为直接维护 llm/db/report 目录
- 修复从仓库目录直接运行时的导入路径问题
- 增加后端单元测试，覆盖 LLM fallback、数据库 upsert 和报告输出

## 参考项目
- MiroFish：LLM JSON 调用、报告流水线、仿真输出组织
- camel-ai/oasis：SQLite schema 与社交仿真数据持久化
- modelscope/agentscope：多厂商模型适配边界

## 验证
- [x] python -m unittest tests.test_backend_modules
- [x] python -m compileall .

## 注意
- 本 PR 不推送到 main，使用 feat/backend-template 分支
- 本 PR 聚焦后端基础能力，不改动 UI 视觉方案
```
