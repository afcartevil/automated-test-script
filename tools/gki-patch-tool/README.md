# GKI Patch Tool

面向 Android GKI 内核 patch 的**批量分析、可视化报告、死机诊断与升级合入**工具。支持 **CLI 独立运行** 与 **Web 交互平台**（Vue 前端 + FastAPI 后端）。

📄 **产品说明**：[gkiPatchTool_产品说明.md](gkiPatchTool_产品说明.md) · [HTML 版](gkiPatchTool_产品说明.html)

---

## 快速启动

```bash
# Windows
run_windows.bat

# Linux / Ubuntu
chmod +x run_linux.sh
./run_linux.sh
```

启动后浏览器访问：**http://127.0.0.1:8000/app/**

首次启动会自动安装 Python 依赖并构建前端（`frontend/dist`）。

---

## Web 平台功能

顶部导航：**首页 · 看板 · patch分析 · 故障诊断 · patch入库 · 数据库 · 设置**

| 页面 | 路径 | 主要能力 |
|------|------|----------|
| 首页 | `/app/` | 功能入口、环境配置概览 |
| 看板 | `/app/dashboard` | 分析/升级任务统计、最近任务 |
| patch分析 | `/app/analysis` | 单 SHA / tag 区间分析、结果浏览 |
| 故障诊断 | `/app/crash` | 死机日志 → 疑似 patch → LLM 归因 |
| patch入库 | `/app/upgrade` | GKI 升级合入、冲突 AI、编译验证 |
| 数据库 | `/app/patches` | 全库 patch 浏览、筛选、详情预览 |
| 设置 | `/app/settings` | 本地代码路径、LLM、升级默认配置 |

### patch 分析（`/app/analysis`）

- **任务模式**：单 SHA 或 tag 区间；支持采样数量、强制重新分析
- **实时进度**：WebSocket 推送采集 / LLM / 子 tag 等阶段进度
- **结果页锚点导航**：分析总结 · 子 tag 分析 · 模块分析 · 测试建议 · 后续修复 · 高风险 · Patch 列表
- **分析总结**：区间文字综述、覆盖率、统计、标签分布
- **分模块 LLM 分析**：按开发模块聚合；大模块 diff 过大时**自适应 chunk 拆分**，rollup 汇总；展示 chunk 摘要与代码树
- **子 tag 累计分析**：同月 `_rN` 子 tag 按 **r1→r2、r1→r3…** 累计区间统计，推荐最优合入子 tag；可展开查看区间内全部 patch
- **后续 Fixes 汇总**：列出「引入问题且后续 tag 有 Fixes 修复」的 patch，可一键跳转
- **Patch 列表**：按模块 / LLM·脚本 / 后续修复筛选；展开查看 HTML 详情报告
- **报告导出**：在线查看 / 下载 HTML 报告、区间 Diff

### patch 数据库（`/app/patches`）

- 顶部统计：Patch 总量、模块数、全库均分
- 搜索 SHA / 标题；模块下拉与快捷 chips 筛选（「未分类」与「全部」独立区分）
- 左侧列表仅显示 **SHA + 标题**；右侧详情面板展示完整分析报告
- Patch 详情：结构化头部（得分、推荐、已知缺陷、后续修复 tag 等）、Commit 原文折叠、评分明细与 diff

### patch 入库（`/app/upgrade`）

表单分块：**Tag 区间 · 目标仓库 · 执行方式 · 自动化选项 · 编译配置**

- 本地或 **cqris 远程 SSH** 合入（混合模式：冲突/编译修复可走本地映射）
- 自动提交、**AI 冲突合入**、自动编译、**AI 编译修复重试**
- 右侧任务详情：阶段进度、冲突面板（Gerrit diff）、编译修复记录

### 故障诊断（`/app/crash`）

- 粘贴死机日志或上传文件；支持已有分析结果跳过 phase1
- 两阶段：疑似 patch 检索 → LLM 归因；历史记录与 HTML 报告下载

### 设置（`/app/settings`）

- 本地 GKI 代码路径（commit/diff 查询）
- LLM API Key / Base / Model（可从服务端拉取模型列表）
- 升级与编译默认参数

---

## CLI 使用

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 运行时配置（`gki-patch-tool.yaml`）

| 配置块 | 说明 |
|--------|------|
| `repo.url` / `repo.dir` | 远程仓库 URL、本地 clone 路径 |
| `scoring.config` | 评分规则 YAML 路径 |
| `analysis.*` | workers、chunk_size、retry 等 |
| `output.dir` | 默认输出目录 |
| `llm.*` | LLM API（CLI 脚本合并分析时使用） |
| `target_repo.*` / `upgrade.*` / `build.*` | 升级合入与编译 |

**优先级**：命令行参数 > 环境变量（`GKI_*`）> `gki-patch-tool.yaml` > 内置默认值。

默认评分规则：`config/scoring-config.yaml`

### 3. 区间分析

```bash
python tools/patch_analyzer.py \
  --from-tag android14-6.1-2025-12_r14 \
  --to-tag android14-6.1-2026-03_r8 \
  --output outputs/result.json
```

### 4. 单 commit 分析

```bash
python tools/patch_analyzer.py \
  --commit 821e986d6073e681771592067e649d191ff3ebae \
  --output outputs/single.json
```

### 5. 生成 HTML 报告

```bash
python tools/render_report.py --input outputs/result.json --output outputs/result.html
python tools/render_report_llm.py --input outputs/result.json --output outputs/result-llm.html
```

### 6. JSON 输出字段（摘要）

- 区间信息、总量/已分析/失败、`summary`、每笔 `patches[]`
- 每笔含：`score`、`score_details`、`recommendation`、`test_suggestions`、`fix_in_future`（后续 Fixes）、`dev_module` 等

### 7. GKI 升级合入（CLI）

```bash
python tools/upgrade_runner.py start \
  --from-tag android12-5.10-2025-06_r4 \
  --to-tag android12-5.10-2025-12_r4 \
  --target-repo /path/to/vendor/kernel \
  --wait

python tools/upgrade_runner.py continue --job-id <id> --commit --build
python tools/upgrade_runner.py status --job-id <id>
```

合入方式：`format-patch`（git am）或 `squash`（git apply）。合入前自动创建备份分支。

---

## Linux 服务器部署

```bash
chmod +x run_server.sh
./run_server.sh          # 安装依赖 + 构建前端 + 后台启动
./run_server.sh status
./run_server.sh logs
./run_server.sh stop
```

| 变量 | 说明 | 默认 |
|------|------|------|
| `GKI_HOST` | 监听地址 | `0.0.0.0` |
| `GKI_PORT` | 端口 | `8000` |
| `GKI_REPO_DIR` | 上游 kernel 路径 | yaml |
| `GKI_TARGET_REPO_DIR` | vendor 内核路径 | yaml |

Web 无内置登录，生产环境建议内网或前置认证。

---

## 注意事项

- Google Source 有速率限制，区间分析建议 `--workers 4~6`、`--chunk-size 50~100`
- 修改前端后需重新构建：`cd frontend && npm run build`（或由 `run_linux.sh install` 完成）
- 子 tag 分析、模块 chunk 覆盖率等新字段需**重新分析任务**后才会出现在旧任务中
- 更完整的架构与模块说明见 [`gkiPatchTool_OVERVIEW.md`](gkiPatchTool_OVERVIEW.md)
