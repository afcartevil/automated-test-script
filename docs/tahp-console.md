# TAHP Console 使用指南

TAHP Console 是基于 Hermes Web UI 叠加 TAHP 业务面板的可视化控制台，供团队同事在不使用 Claude Code CLI 的情况下操作 TAHP 的全部功能。

---

## 架构概览

```
浏览器 (Vue 3 + Pinia)
    │  HTTP REST + Socket.IO
    ▼
BFF (Koa 2, port 8650)
    ├── /api/tahp/*      ─── TAHP REST 路由
    ├── /api/hermes/*    ─── Hermes 原生路由（保留）
    └── Socket.IO /tahp-run ─── 任务进度流
           │
           ▼
    McpBridge (长连进程)
           │  stdio JSON-RPC 2.0
           ▼
    tahp-mcp-server/server.py  (9 个 MCP 工具)
           │
           ▼
    constraints/ playbooks/ knowledge-base/ reports/
```

控制台与 `tahp-mcp-server` 通过标准 MCP stdio 协议通信，和 Claude Code 复用同一个 server.py，无代码分叉。

---

## 快速启动

### 前置要求

- Node.js >= 20
- Python **3.11+**（`hermes-agent-main` 与 `tahp-mcp-server` 共用，可用 `TAHP_PYTHON` 指定）
- 仓库根目录包含 **`hermes-agent-main/`**（完整 hermes-agent 源码，含 `run_agent.py`）

### 安装与启动

```bash
# 在 tahp 主仓根目录下执行
cd tahp-console

# 安装依赖（含 MCP + 内置 hermes-agent venv 初始化）
npm install
npm run setup
```

首次 `setup` / `dev` / `start` 会自动：

1. 在 `hermes-agent-main/.venv` 创建虚拟环境并 `pip install -e .`
2. 写入 `tahp-console/.tahp/agent-paths.json` 与 `.env` 中的 `HERMES_AGENT_ROOT` 等变量
3. 在终端打印进度（拷贝到新电脑后同样执行一次即可）

可选完整依赖（较慢）：`npm run setup:agent -- --full`

**首次启动** 在安装 venv 后会**非阻塞**完成：

1. 若 `config.yaml` 无 `terminal.backend`，自动写入默认值 `local`
2. 在终端打印一次性提示（API Key 请用 Web「模型管理」配置）

**注意：** 请勿跨电脑拷贝 `hermes-agent-main/.venv`（会指向旧机器的 Python 路径）。新电脑应删除 `.venv` 后让脚本自动重建，或执行 `npm run setup:agent -- --force`。

Agent 安装失败时，`npm run dev` **仍会启动 Web UI**（`--optional`）；Bridge / Bug 分析需 Agent 就绪后才可用。

不阻塞启动。跳过提示：`TAHP_SKIP_HERMES_SETUP_WIZARD=1`  
强制重装 Agent venv：`npm run setup:agent -- --force`

```bash
# tahp-mcp-server 的 Python 依赖（若 setup 提示未就绪）
pip install mcp pyyaml
```

### 开发 / 生产启动

```bash
# 开发模式（热更新）
npm run dev
# → client: http://localhost:5173
# → server: http://localhost:8650

# 生产模式
npm run build
npm run start
# → http://localhost:8650

# 守护进程管理
node bin/tahp-console.mjs start    # 后台启动
node bin/tahp-console.mjs status   # 查看运行状态
node bin/tahp-console.mjs stop     # 停止
node bin/tahp-console.mjs restart  # 重启
```

### 环境变量

复制 `.env.example` 为 `.env` 并按需修改：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PORT` | `8650` | 服务端口 |
| `AUTH_DISABLED` | `1` | `1`=免鉴权，`0`=启用令牌验证 |
| `AUTH_TOKEN` | — | 设置后自动启用令牌模式 |
| `TAHP_PROJECT_ROOT` | 自动探测 | TAHP 主仓目录（含 `tahp-mcp-server/`） |
| `TAHP_PYTHON` | `python` | Python 可执行路径 |
| `HERMES_AGENT_ROOT` | 自动（见 `.tahp/agent-paths.json`） | 内置 `hermes-agent-main` 路径 |
| `HERMES_AGENT_BRIDGE_PYTHON` | 自动 | Bridge 使用的 venv Python |
| `HERMES_BIN` | 自动 | venv 内 `hermes` CLI |
| `TAHP_SKIP_AGENT_SETUP` | — | 设为 `1` 可跳过 `predev`/`prestart` 的 Agent 初始化 |
| `LOG_LEVEL` | `info` | 日志级别 (debug/info/warn/error) |

`TAHP_PROJECT_ROOT` 自动探测逻辑：从 `tahp-console/` 向上遍历父目录，找到含 `tahp-mcp-server/server.py` 的目录。

---

## 视图清单

### 仪表盘 (`/tahp/dashboard`)

总览面板：
- **4 个模块状态卡**：telephony / kernel-driver / power-mgmt / shared，显示各模块约束域数量
- **最近任务列表**：最新 5 个任务状态（运行中/成功/失败）
- 点击卡片跳转对应模块的矩阵或任务

### 启动任务 (`/tahp/task-executor`)

交互式任务启动：
1. 选择**模块**（telephony / kernel-driver / power-mgmt）
2. 选择**域**（bug_analysis / code_adaptation / ...）
3. 输入**设计文档路径**（相对于项目根的 Markdown 或文本文件路径）
4. 点击"启动"后右侧实时显示进度流
5. 任务失败或需要调整时，点击**纠偏**按钮输入指导意见后重试

实时事件流通过 Socket.IO `/tahp-run` 命名空间推送，阶段变更、工具调用、完成状态逐条显示。

### 任务列表 (`/tahp/tasks`)

- 全量历史任务表格，含状态徽章（运行中/成功/失败/纠偏中）
- 支持按模块/状态筛选
- 点击任意任务行可查看详情或触发纠偏

### 模块矩阵 (`/tahp/modules`)

4 × N 矩阵（模块 × 约束域）：
- 绿色单元格：约束文件已存在，点击直接进入编辑器
- 灰色单元格：约束文件缺失，提示如何创建

### 约束编辑器 (`/tahp/constraint-editor/:module/:file`)

- **Monaco YAML 编辑器**，语法高亮 + 错误标注
- **验证**按钮：调用 `scripts/validate_constraints.py --strict` 做 dry-run，失败时显示错误详情
- **保存**按钮：验证通过后写入磁盘；如验证失败，弹确认对话框才允许强制保存
- 支持快捷键 Ctrl+S 触发保存

### 质量门禁 (`/tahp/gate-check`)

手动触发门禁检查：
- 选择模块 + 检查级别（P0 / P1 / P2 / ALL）
- 可选：填入任务 ID 只检查特定任务产出
- 结果按 P0（红）/ P1（橙）/ P2（黄）颜色编码
- 违规列表支持点击跳转到对应约束文件

### 知识库 (`/tahp/knowledge`)

语义检索：
- 输入查询文本，选择模块过滤（可选），调整 top_k（默认 5）
- 结果卡片显示：相似度分数、模块标签、内容摘要
- 调用 `tahp_query_knowledge` MCP 工具

### Playbooks (`/tahp/playbooks`)

Pipeline 查看器：
- 左侧列表：扫描 `playbooks/` 目录下所有 YAML
- 右侧：Monaco YAML 只读预览

### 工具箱 (`/tahp/tools`)

三个底层工具的单步调用面板：

| 标签 | 工具 | 输入 |
|------|------|------|
| 日志分析 | `tahp_analyze_log` | 日志内容 |
| 代码审查 | `tahp_code_review` | 代码片段 |
| API 迁移 | `tahp_api_migration` | 旧 API 名称 |

结果以格式化 JSON 展示。

### 报告 (`/tahp/reports`)

报告浏览器：
- 左侧：递归扫描 `reports/` 目录树
- 右侧：Monaco 文件查看器，自动识别 JSON/YAML/Markdown 语法高亮
- 支持 JSONL 格式（trace 文件）友好渲染

### 通用 Chat（Hermes 原生）

侧栏底部的"通用 Chat"工作区保留 Hermes 全套 Chat / Sessions / Models / Skills / Files / Logs / Terminal / Jobs 视图，需配置 LLM Provider 方可使用。

---

## 接入新模块

### 1. 初始化约束目录

```bash
# 在 tahp 主仓根目录
python scripts/init_module.py --module your-module --owner your-name
```

### 2. 编写 module.yaml

编辑 `constraints/your-module/module.yaml`，填写 `scope.includes` 和 `scope.excludes`。

### 3. 控制台立即可见

启动/刷新控制台，模块矩阵会自动显示新模块的约束域格子（灰色=待创建，点击会给出创建提示）。

### 4. 添加约束域文件

在控制台矩阵页点击空格子，会提示对应域文件路径；手动创建或使用模板后刷新即可变为可编辑状态。

---

## 常见问题

### MCP Bridge 启动失败

**症状**：所有 TAHP API 返回 `503 MCP bridge not available`

**排查**：
```bash
# 手动测试 MCP server 可运行
cd <tahp-project-root>
python tahp-mcp-server/server.py
# 输入 {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","clientInfo":{"name":"test","version":"0.1"},"capabilities":{}}}
# 应返回 initialize result
```

常见原因：
- `TAHP_PROJECT_ROOT` 路径不正确
- `TAHP_PYTHON` 不是有效的 Python 3 路径
- Python 缺少 `mcp` 依赖（`pip install mcp pyyaml`）

### 端口 8650 被占用

```bash
# Windows
netstat -ano | findstr 8650
# 改用其他端口
PORT=8651 npm run start
```

### 约束保存报 schema 错误

编辑器中点击**验证**查看详细错误，或运行：
```bash
python scripts/validate_constraints.py constraints/<module>/<file>.yaml --strict
```

### 知识库查询无结果

检查 `knowledge-base/` 目录是否有向量索引文件；如需重建：
```bash
python scripts/feed_knowledge.py constraints/<module>/ --rebuild
```

---

## 升级 Hermes 基础版本

控制台叠加在 Hermes Web UI 之上，升级时需注意以下冲突点：

| 文件 | 改动类型 | 注意事项 |
|------|----------|----------|
| `packages/client/src/router/index.ts` | 重写 | 需重新合入 `/tahp/*` 路由组 + `authDisabled` 默认值改动 |
| `packages/client/src/components/layout/AppSidebar.vue` | 改动 | 需保留 TAHP 导航分组 |
| `packages/client/src/views/LoginView.vue` | 改动 | 需保留 `/tahp/dashboard` 重定向 |
| `packages/server/src/routes/index.ts` | 改动 | 需保留 `registerTahpRoutes(app)` 调用 |
| `packages/server/src/index.ts` | 改动 | 需保留 `initTahpBridge()` + `setupTahpRunSocket()` 调用 |
| `vite.config.ts` | 改动 | 需保留端口 8650 |
| `package.json` | 改动 | 需保留 `name`/`bin`/`setup` 改动 |
| `bin/tahp-console.mjs` | 新增 | 不在 Hermes 原版中，不会冲突 |
| `packages/*/tahp/` 下所有新增文件 | 新增 | 不在 Hermes 原版中，不会冲突 |

升级步骤：保留 `tahp/` 命名空间下的所有新增文件 → 重新 apply 以上 7 个改动文件的 diff → `npm install` → 验证。
