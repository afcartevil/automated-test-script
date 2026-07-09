# TAHP Console 使用指南

TAHP Console 是基于 Hermes Web UI 叠加 TAHP 业务面板的可视化控制台，通过 Hermes Agent + Skill 执行智能诊断与 AI 适配调试。

---

## 架构概览

```
浏览器 (Vue 3 + Pinia)
    │  HTTP REST + Socket.IO
    ▼
BFF (Koa 2, port 8650)
    ├── /api/tahp/*      ─── TAHP REST 路由
    ├── /api/hermes/*    ─── Hermes 原生路由
    └── Socket.IO /tahp-run ─── Agent 任务进度流
           │
           ▼
    Hermes Agent Bridge → hermes-agent-main/
           │
           ▼
    skills/  knowledge-base/  reports/
```

---

## 快速启动

### 前置要求

- Node.js >= 20
- Python **3.11+**（`hermes-agent-main` 使用，可用 `TAHP_PYTHON` 指定）
- 仓库根目录包含 **`hermes-agent-main/`** 与 **`skills/.claude/skills/`**

### 安装与启动

```bash
cd tahp-console
npm install
npm run setup
npm run dev
# → client: http://localhost:5173
# → server: http://localhost:8650
```

生产模式：

```bash
npm run build
npm run start
node bin/tahp-console.mjs start
```

### Windows 托盘（方案 C）

双击仓库根目录 `run_adapter.bat` 成功后，会自动在系统托盘显示 **EasyAdapter** 图标（与浏览器 Tab 相同的紫底 EA 图标）。

**右键菜单**：

| 菜单项 | 说明 |
|--------|------|
| 打开控制台 | 浏览器打开 `http://localhost:8650` |
| 重启服务 | 快速 `tahp-console restart`（不拉代码） |
| 更新并重启 | 无闪窗静默执行 `run_adapter.bat` 全链路（研发用） |
| 停止服务 | 停止后台 BFF |
| 查看日志 | 打开 `%USERPROFILE%\.tahp-console\server.log` |
| 关闭程序 | 停止服务并退出托盘 |

- 仅启动托盘（服务已运行时）：双击 `启动托盘.bat`
- 禁用自动托盘：设置环境变量 `TAHP_TRAY=0`
- 重新生成图标：`cd tahp-console && npm run tray:icon`

开机自启（`开机自启-注册.bat`）会通过 `run_adapter.bat` 一并拉起服务与托盘。

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PORT` | `8650` | 服务端口 |
| `AUTH_DISABLED` | `1` | `1`=免鉴权，`0`=启用令牌验证 |
| `AUTH_TOKEN` | — | 设置后自动启用令牌模式 |
| `TAHP_PROJECT_ROOT` | 自动探测 | 含 `skills/.claude/skills` 或 `knowledge-base/` 的目录 |
| `TAHP_PYTHON` | `python` | Python 可执行路径 |
| `HERMES_AGENT_ROOT` | 自动 | 内置 `hermes-agent-main` 路径 |
| `LOG_LEVEL` | `info` | 日志级别 |
| `TAHP_TRAY` | `1` | `0` 禁用 run_adapter 后自动启动系统托盘 |

---

## 视图清单

### 仪表盘 (`/tahp/dashboard`)

- 聚合 Bug 分析任务与适配报告统计
- 近 7 天任务趋势
- 模块矩阵快捷入口（跳转智能诊断或 AI 适配调试）

### 智能诊断 (`/tahp/bug-analysis`)

- 输入 JIRA key 或描述，由 Agent + Skill 执行 Bug 分析
- 实时进度通过 Socket.IO 推送
- 报告落盘 `reports/bug-analysis/`

### AI 适配调试 (`/tahp/adapt-debug`)

- 选择适配域与表单参数，启动 `agent-run`
- 实时任务流 + 报告入口

### 知识库 (`/tahp/knowledge`)

- 知识条目 CRUD、草稿审核、BM25 语义搜索
- 数据存储于 `knowledge-base/.kb-data`

### 报告 (`/tahp/reports`)

- 浏览 Bug 分析与适配 Agent 任务报告

### Hermes 原生

侧栏保留对话、Skills 库、模型管理、终端等 Hermes 功能。

---

## 验证

```bash
cd tahp-console
npm test
```

---

## 常见问题

### Agent Bridge 不可用

检查 `hermes-agent-main/.venv` 是否已安装：`npm run setup:agent -- --force`

### 端口 8650 被占用

```bash
PORT=8651 npm run start
```

### 知识库搜索无结果

确认 `knowledge-base/.kb-data` 有数据，或在知识库页面创建/导入条目。
