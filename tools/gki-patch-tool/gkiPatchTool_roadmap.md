# gkiPatchTool 工程化改进路线图

> 导出时间：2026-05-26（后续增量见下方「已实现」）  
> 来源：Qoder Memory - important_decision_experience

---

## 已实现（2025–2026 Web 平台）

以下能力已在当前工程中落地，详见 [`README.md`](README.md) 与 [`gkiPatchTool_OVERVIEW.md`](gkiPatchTool_OVERVIEW.md)：

- **SQLite 存储**：tasks / patches / upgrade_jobs / config；SHA 级复用
- **Web 交互界面**：Vue 3 SPA（`/app/`）+ FastAPI + WebSocket 进度
- **按模块 / 评分筛选**：patch 分析页、数据库页、模块 LLM rollup
- **子 tag 累计分析**：r1→rN 区间推荐与 patch 列表展开
- **后续 Fixes 扫描与 UI 汇总**
- **分模块 diff 自适应 chunk**，避免大模块静默截断
- **GKI 升级合入全流程**：冲突 AI、编译 AI 修复、远程 SSH

---

## P0 - SQLite 存储（最高优先级）✅ 已完成

- **痛点**：单文件 JSON（100条就1.4MB）无法扩容到全量分析（~2000条），无法增量更新和按维度查询
- **方案**：引入 Python 内置 sqlite3，设计表结构：
  - `patches` 表：每条patch元信息 + 脚本评分
  - `llm_analysis` 表：LLM分析结果（1:1）
  - `scores` 表：各维度评分明细
  - `tags` 表：标签分类
- **价值**：零外部依赖，支持 SQL 查询（如"networking子系统中风险评分>7的patch"），方便多tag区间对比

---

## P1 - 模块化重构

- **痛点**：`patch_analyzer.py` 达2815行，单文件难以维护和扩展
- **方案**：拆分为 analyzer 包
  - `analyzer/scanner.py`：代码扫描
  - `analyzer/scorer.py`：评分引擎
  - `analyzer/rules/`：YAML规则加载
  - `analyzer/reporters/`：输出格式（JSON/HTML/SQLite）
- **价值**：各模块独立测试和扩展

---

## P2 - 多tag区间对比分析

- 目前只对比一个区间（06_r4 → 12_r4）
- 扩展为连续跟踪多个 LTS 版本（06→09→12→15_r4）
- 生成趋势报告：patch类型分布、风险趋势、模块热度
- 识别"同一上游fix在多个区间重复出现"的patch

---

## P3 - 自动化CI流水线

- 定时任务：每周/每月自动拉取新tag、分析、生成报告
- 增量分析：只分析新出现的patch，已有的跳过
- 告警机制：检测到高风险patch（内存泄露、安全漏洞）时发通知

---

## P4 - 交互式查询界面 ✅ 已基本完成

- FastAPI + Vue 数据库浏览、模块筛选、详情预览
- 后续可增强：趋势图表、更复杂 SQL 聚合

---

## LLM分析质量提升（贯穿各阶段）

- 结构化打分：让LLM也给出各维度评分，与脚本评分交叉验证
- 多模型对比：支持对比不同LLM分析结果
- 分析缓存复用：相同patch的LLM分析可缓存，避免重复消耗
