# 路线图

## 当前版本（v0.1）

- [x] 供应链场景搭建（Step 01）
- [x] 行为体决策配置（Step 02）
- [x] 7 行为体 LLM 仿真引擎
- [x] 6 种关键事件检测
- [x] 程序化六维方案评分
- [x] Markdown / PDF 报告导出
- [x] RAG 文档导入与知识检索
- [x] SQLite 持久化与检查点恢复
- [x] 多厂商 LLM fallback

---

## 短期（v0.2）

### 图表可视化
- **文件**：`report/charts.py`
- **内容**：接入 pyqtgraph，实现方案对比曲线图和六维雷达图
- **负责人**：csf

### LLM 深度评估
- **文件**：`llm/prompts.py`（`STRATEGY_EVALUATION_SYSTEM`、`REPORT_GENERATION_SYSTEM`）
- **内容**：用 LLM 替代程序化公式，生成可解释的评分和报告
- **依赖**：图表模块完成后接入 `ui/result_page.py`

---

## 中期（v0.3）

- [ ] 行为体按需创建（`AgentFactory.create_by_ids`）
- [ ] 行为体模板 UI 编辑（`AgentFactory.get_template`）
- [ ] 仿真指标加权聚合优化（`_weighted_average`）
- [ ] 自定义供应链节点参数编辑
- [ ] 仿真回放与单步调试

---

## 长期

- [ ] 多供应链场景对比
- [ ] 历史推演结果检索与对比
- [ ] 行为体行为模式学习（基于历史仿真数据）
- [ ] Web 版 / 协作推演

---

## 变更记录

| 日期 | 变更 |
|------|------|
| 2026-07-15 | 从舆情推演改造为供应链决策推演，整理路线图 |
