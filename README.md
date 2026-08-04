# Prism

**棱镜折射 · 透视供应链连锁反应**

面向供应链管理者的桌面端演化沙盘。构建供应链网络，配置 7 类行为体的性格与种子事件，通过 LLM 多行为体互动仿真，观察决策沿供应链折射演化的连锁影响——在真实执行前，透视世界的演化走向。

## 工作流

```
供应链搭建 → 行为体性格配置 → 多行为体仿真 → 演化分析 → 导出报告
```

1. **供应链搭建** — 定义行业、节点、初始库存/成本/服务水平，导入背景文档，可由 AI 分析文档自动填写
2. **行为体性格配置** — 调整 7 类行为体的决策倾向/活跃度/影响力/画像，配置注入世界的种子事件，可由 AI 一键生成
3. **多行为体仿真** — 7 类行为体（供应商→制造商→分销商→零售商→物流→消费者→监管）在单一世界中互动推演，实时显示库存/成本/服务水平/利润率/交付延迟
4. **演化分析** — 深色结论横幅、AI 综合分析、指标演化曲线、六维雷达、演化过程泳道图，导出 Markdown

## 核心特性

- **全链路 AI 集成**：Step1 文档分析自动填写场景、Step2 AI 生成行为体配置、Step3 行为体决策、Step4 AI 叙述式综合分析（失败自动降级为公式报告）
- **全局设置页**：7 家厂商预设（Anthropic / DeepSeek / Kimi / OpenAI / 通义千问 / 智谱 / 自定义，按品牌名字母序），统一生效厂商，仿真轮次/决策温度/超时/重试可视化配置
- **多行为体 LLM 仿真**：每个行为体由独立 LLM prompt 驱动，根据全局状态自主决策
- **行为体互动**：行动信息流 + 个性化观察层，行为体感知上下游邻居行动并显式回应，跨轮形成反应链
- **种子事件注入**：世界干预在指定周期进入信息流，沿供应链链路传播扩散（MiroFish initial_posts 式）
- **关键事件系统**：5 种供应链事件（断供、爆仓、价格战、监管介入、需求激增）动态触发
- **演化分析**：AI 综合分析 + 指标演化曲线 + 六维雷达图 + 行为体×周期泳道图
- **检查点恢复**：每轮自动持久化，中断后可无缝继续
- **RAG 知识检索**：导入 PDF/Word/Markdown 文档，仿真中自动检索相关背景

## 快速开始

```bash
pip install -r requirements.txt
python main.py          # 启动后在「设置」页填写 LLM API Key 并保存
```

在「设置」页保存的 API Key 会存入操作系统钥匙串（macOS 钥匙串 / Windows 凭据管理器），不落盘明文；无钥匙串后端的环境会改用本机特征派生密钥加密后存 `.env`（`enc:v1:` 前缀）。开发调试也可在 `.env`（复制自 `.env.example`）手动填明文 Key，启动后会自动迁移。

## 桌面端打包（GitHub Actions）

推送版本标签即可自动构建 macOS / Windows 安装包并发布到 GitHub Releases：

```bash
git tag v0.1.0
git push origin v0.1.0
```

也可以在 Actions 页面手动运行 **Build Desktop Apps** workflow，或在推送到 main 时自动做验证构建（产物以 Artifact 形式提供）。

产物：

- macOS：`prism-macos-arm64.dmg`（Apple Silicon）
- Windows：`prism-windows-x64.zip`（解压后运行 `Prism/prism.exe`）

注意事项：

- 应用**未做代码签名/公证**。macOS 首次打开请右键 → 打开（或执行 `xattr -dr com.apple.quarantine /Applications/Prism.app`）；Windows SmartScreen 提示时选择「仍要运行」。如需签名，需额外配置 Apple Developer 证书等 secrets 并扩展 `.github/workflows/build.yml`。
- 数据库存放于用户数据目录：macOS `~/Library/Application Support/Prism/`，Windows `%APPDATA%/Prism/`。
- 打包后的应用按「用户数据目录 → exe 同目录 → 运行目录」顺序查找并加载首个 `.env`（非敏感配置参照 `.env.example`），推荐放在上述用户数据目录；API Key 请在应用「设置」页填写，会保存到系统钥匙串而非 `.env`。
- 本地打包：`pip install pyinstaller && pyinstaller prism.spec --noconfirm`（macOS 产出 `dist/Prism.app`，Windows 产出 `dist/Prism/`）。

## 技术栈

| 用途 | 技术 |
|------|------|
| 桌面 UI | PySide6 |
| LLM 调用 | OpenAI-compatible / Anthropic SDK（7 家厂商预设，统一生效厂商） |
| 数据存储 | SQLite（WAL 模式） |
| 报告导出 | Markdown |
| 文档解析 | pypdf + python-docx |
| 配置管理 | python-dotenv |

## 项目结构

```
prism/
├── main.py
├── config.py
├── assets/
│   ├── fonts/                  # 内嵌字体
│   └── icons/                  # 应用图标
├── ui/                          # PySide6 界面
│   ├── main_window.py
│   ├── title_bar.py              # 自定义标题栏（macOS / Windows）
│   ├── home_page.py
│   ├── settings_page.py         # 设置 — 全局 LLM 配置与仿真参数
│   ├── process_page.py          # 4 步工作流协调
│   ├── event_page.py            # 供应链搭建（Step 01）
│   ├── persona_page.py          # 行为体性格配置（Step 02）
│   ├── simulation_page.py       # 仿真运行（Step 03）
│   ├── result_page.py           # 演化分析（Step 04）
│   ├── ai_worker.py             # 通用 AI 调用工作线程
│   ├── charts.py                # 折线图 / 雷达图 / 泳道图组件
│   ├── widgets.py
│   └── styles.py
├── core/                        # 仿真引擎 + 行为体 + 事件
│   ├── agent.py
│   ├── agent_factory.py
│   ├── action_feed.py           # 行动信息流（行为体互动）
│   ├── document_importer.py
│   ├── scenario_parser.py
│   ├── simulation_engine.py
│   ├── text_utils.py            # 发言标点规范化
│   ├── world_state.py
│   └── events.py
├── llm/                         # LLM 客户端 + 配置 + 业务调用 + Prompt
│   ├── client.py
│   ├── config.py
│   ├── analysis.py
│   └── prompts.py
├── report/                      # 报告生成 + 导出 + 时间线
│   ├── generator.py
│   ├── timeline.py
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

MIT License — 详见 [LICENSE](LICENSE)
