# gkiPatchTool 工具说明文档

> 面向需要了解 gkiPatchTool 整体情况的技术人员。  
> 更新时间：2026-06-30

---

## 1. 工具概述

**gkiPatchTool** 面向 Android GKI 内核 patch，提供从**区间分析 → 风险评估 → 死机诊断 → vendor 合入**的完整工具链。

| 模式 | 说明 |
|------|------|
| **CLI** | `tools/patch_analyzer.py` 等脚本，适合批量导出、CI 集成 |
| **Web** | FastAPI + SQLite + WebSocket；**Vue 3 前端**（`/app/`） |

---

## 2. 核心功能

### 2.1 补丁分析引擎（CLI + Web 共用）

| 能力 | 说明 |
|------|------|
| 区间 / 单 SHA 分析 | 从 android.googlesource.com 抓取 commit 与 diff |
| 多维评分 | `scoring-config.yaml` 驱动；10 分制 + 评分明细 + 测试建议 |
| 标签与模块 | patch 类型标签 + 21 类 `dev_module` 路径映射 |
| 后续 Fixes 扫描 | 扫描区间内 patch 的 `Fixes:` 引用，标记 `fix_in_future` |
| 死机模式 / crash_risk | 规则 + LLM 评估高风险路径 |
| 并发与采样 | workers、chunk-size、区间采样 |

### 2.2 Web — patch 分析页

**任务管理**：创建区间/单 SHA 任务、历史列表、批量删除、WebSocket 进度、取消任务。

**结果展示**（分析完成后）：

- **锚点导航**：分析总结、子 tag、模块分析、测试建议、后续修复、高风险、Patch 列表
- **分析总结**：文字综述、分层覆盖率（patch / 模块 / chunk）、统计与标签
- **分模块分析**（LLM）：
  - 每模块：修改解读、影响范围、问题闭环、代码变化、代码树、测试建议、死机风险
  - **大模块 diff 截断时**：自适应 chunk 拆分 + 高风险 patch diff 补强 + chunk 摘要 rollup（map-reduce），避免 LLM 输入被静默截断
- **子 tag 累计分析**：
  - 同月 `_rN` 子 tag 生成 **r1→r2、r1→r3…** 累计区间
  - r1→rMax 区间 patch **只分析一次**，各子区间做统计切片；持久化 `monthly_subtag_results`
  - 推荐综合风险最低的子 tag；表格可展开查看区间内全部 patch
- **后续 Fixes 汇总**：`future_fix_patches` 列表，含修复 tag、引入摘要
- **Patch 列表**：模块筛选、后续修复筛选、展开 HTML 详情

**数据复用**：patch 以 SHA 为主键；相同 SHA 跨任务复用 LLM/脚本结果。

### 2.3 Web — patch 数据库页

- 全库 patch 分页浏览（`/api/patches`）
- 统计卡片、搜索、模块筛选（含「未分类」专用过滤 `__empty__`）
- 左侧 **SHA + 标题** 列表；右侧内嵌 patch HTML 报告
- Patch 详情渲染（`render_report_llm.render_patch`）：状态 pill、已知缺陷/后续修复、Commit 折叠、后续修复卡片

### 2.4 Web — patch 入库（GKI 升级）

- 分块表单：Tag、目标仓库、远程 SSH、自动化、编译
- 流程：合入 → 冲突（手动 / **AI 自动合入**）→ 提交 → 编译 → **AI 编译修复重试**
- cqris 远程 + 本地映射混合模式
- 冲突 Gerrit diff 视图、执行日志下载

### 2.5 死机分析

- Phase1：日志特征 → 疑似 patch；Phase2：间接因果 + LLM 归因
- 历史记录、HTML 报告、与 patch 数据库复用

### 2.6 LLM 深度分析

- OpenAI 兼容 API；配置存 SQLite，Web 设置页管理
- 有 LLM 时：采集 → 逐笔 LLM + 分模块 rollup；无 LLM 时走脚本规则
- `llm_service.py`：模块 chunk / rollup / single 分析 prompt；注入高风险 diff 与风险索引

### 2.7 报告与导出

| 类型 | 脚本 / 入口 |
|------|-------------|
| 标准 HTML | `render_report.py` |
| 索引 HTML | `render_report_indexed.py` |
| LLM 增强 HTML | `render_report_llm.py`（Web 单 patch 详情同源） |
| 任务报告 | `GET /api/tasks/{id}/report` |
| 区间 Diff | `GET /api/tasks/{id}/diff` |
| Excel | `export_patch_analysis_to_excel.py` |

---

## 3. 系统架构

```
输入层
  ├── Android Kernel Repo (git / API)
  ├── 用户表单 (Vue → REST)
  ├── 死机日志 / 升级目标仓库
  └── scoring-config.yaml

数据层
  ├── SQLite (tasks / patches / upgrade_jobs / crash / config)
  ├── monthly_subtag_results (embedded 子 tag 结果 JSON)
  └── outputs/ (CLI JSON/HTML)

核心服务 (web_app/)
  ├── analyzer_service.py      分析编排、子 tag 区间、summary、future_fix
  ├── module_analysis_service.py  分模块 LLM + chunk 路径
  ├── module_chunk_service.py    自适应拆分、高风险取证、coverage
  ├── monthly_subtag_service.py  子 tag 累计分析
  ├── llm_service.py             LLM 调用与 prompt
  ├── crash_analysis_service.py
  ├── upgrade_service.py + conflict/build fix
  └── database.py                CRUD

输出层
  ├── Vue SPA (/app/)
  ├── WebSocket 进度
  ├── HTML 报告 / Diff 下载
  └── CLI JSON/HTML
```

### 前端结构（`frontend/src/`）

| 目录 | 说明 |
|------|------|
| `views/AnalysisView.vue` | patch 分析主页面 |
| `views/PatchDatabaseView.vue` | 数据库浏览 |
| `views/UpgradeView.vue` | patch 入库 |
| `views/CrashAnalysisView.vue` | 故障诊断 |
| `components/analysis/` | 总结、Patch 列表、子 tag、模块树、锚点导航等 |

---

## 4. 技术栈

| 层次 | 选型 |
|------|------|
| 后端 | Python 3、FastAPI、uvicorn、sqlite3 |
| 前端 | Vue 3、Vue Router、Pinia、Vite |
| 实时 | WebSocket |
| 分析 | patch_analyzer.py + scoring-config.yaml |
| 报告 | 内联 HTML 模板 |

---

## 5. 关键设计

### 5.1 Patch 与任务解耦

- `patches` 表 SHA 主键；`task_patches` 关联
- 删除任务不删 patch 分析数据

### 5.2 双模分析路径

- 有 LLM：采集 → LLM（含模块 rollup）
- 无 LLM：采集 → 脚本规则评分

### 5.3 模块大 diff 不静默丢失

- 检测 diff 超限时走 chunk 管线，而非截断后仍声称「全量覆盖」
- coverage 字段：`truncated_chunk_count`、`split_exhausted_count`、`coverage_complete`

### 5.4 子 tag 合入建议

- 累计区间对比风险分布、未来修复数、均分
- 结果持久化，刷新页面可从 `monthly_subtag_results` 恢复（不依赖内存 progress）

### 5.5 引入问题与后续 Fixes

- `_scan_future_fixes` 扫描后续 tag 中 `Fixes:` 指向
- UI 汇总 + patch 详情「已知缺陷 / 后续修复」区块

---

## 6. 后续方向（节选）

| 优先级 | 方向 |
|--------|------|
| P0 | `patch_analyzer.py` 模块化拆分 |
| P1 | 多 tag 区间趋势对比（部分能力已在子 tag / extend-stats 落地） |
| P2 | 增量分析、定时 CI |
| P3 | LLM 与脚本评分交叉验证、多模型对比 |

历史路线图见 [`gkiPatchTool_roadmap.md`](gkiPatchTool_roadmap.md)。

---

## 附录：目录结构

```
gki_patch_tool/
├── tools/                    # CLI：分析、报告、升级 runner
├── web_app/                  # FastAPI 后端
│   ├── app.py
│   ├── analyzer_service.py
│   ├── module_*_service.py
│   ├── monthly_subtag_service.py
│   └── (API + WebSocket)
├── frontend/                 # Vue 3 前端 → dist/
├── config/                   # 评分规则、模块分类配置
│   ├── scoring-config.yaml
│   └── dev_modules.txt
├── docs/patch-analysis/      # Patch 分析流程与说明文档
├── gki-patch-tool.yaml
├── README.md                 # 使用说明（本文档的简版）
└── gkiPatchTool_OVERVIEW.md  # 本文档
```

### 启动

```bash
./run_linux.sh              # 或 run_windows.bat
# → http://127.0.0.1:8000/app/
```
