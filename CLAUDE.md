# TAHP — Claude Code 配置

## 项目

TECNO AI Harness Platform (TAHP) — 传音 Android 底软集成部 AI 辅助开发平台。

## 首先阅读

1. [AGENTS.md](AGENTS.md) — 项目导航与模块定位
2. [.cursor/rules/](.cursor/rules/) — **Cursor 编码规范（强制）**，尤其：
   - `00-change-control.mdc` — 变更范围与敏感链
   - `tahp-verify-commit.mdc` — 验证与提交

执行编码任务前须遵守上述规则；域规则按文件 glob 自动加载。

---

## 架构分层

```
tahp-console (Vue + Koa BFF :8650)
    │
    ├── Hermes Agent Bridge ── hermes-agent-main/
    ├── TaskStream (Socket.IO /tahp-run)
    ├── knowledge-base/ (BFF 自管 + BM25)
    ├── jira_workspace/ (JIRA 日志工作区，工程根下)
    └── reports/
    │
    ▼
skills/.claude/skills/  ← 业务 Skill 运行时目录（同步中心落盘，不入库）
```

**生产路径**：智能诊断、AI 适配调试、知识库、报告、AI 自检均通过 Console BFF 驱动 Hermes Agent 或本地服务，不再经过 MCP stdio 桥。

**Windows 交付**：`run_adapter.bat` + 系统托盘（日常操作）；开机自启见 `tahp-console/scripts/win/`；运行时数据在 `~/.tahp-console/`。

---

## 核心规则

1. **Skill 优先**：业务规则写在 `skills/` 对应 SKILL.md 中
2. **防幻觉**：所有代码产出必须有据可查，禁止编造
3. **最小变更**：只修改与任务直接相关的代码（见 `00-change-control`）
4. **Console 入口**：同事日常使用 `tahp-console`，而非 CLI MCP

### 安全红线

1. 不在未验证 API 存在性的情况下生成代码
2. 不硬编码密钥 / Token / 设备标识
3. 涉及安全相关的 Bug 必须标记为 Critical

---

## 验证命令

```bash
cd tahp-console
npm run setup
npm test
npm run build          # 改 TS/路由/构建链时必跑

# Pre-commit（可选）
powershell -File scripts/pre-commit-check.ps1
```

Console 开发细则：[tahp-console/DEVELOPMENT.md](tahp-console/DEVELOPMENT.md)

---

## tahp-console

```bash
cd tahp-console
npm install
npm run dev            # client:5173, server:8650
npm run build && npm run start
```

环境变量（`.env` 或 shell）：

- `TAHP_PROJECT_ROOT` — TAHP 主仓目录（须含 `tahp-console` 或 `hermes-agent-main` 等标记）
- `TAHP_PYTHON` — Python 可执行路径
- `PORT` — 默认 8650
- `AUTH_DISABLED=1` — 内网免鉴权

面板：仪表盘 / 智能诊断 / AI 适配调试 / 知识库 / 报告 / Skills 库 / 对话 / **AI 自检**

---

## 文件操作范围

详见 `00-change-control.mdc` 分区表。概要：

- 可操作: `skills/`, `knowledge-base/`, `tahp-console/`, `scripts/`, `reports/`
- 谨慎: 路径链文件（`paths.ts`, `jira-workspace.ts`, `unified-config.ts`）
- 禁止: `.git/`, 凭据 `.env`, `hermes-agent-main/` 大范围功能开发, `knowledge-base/.kb-data/` 手改, 将 `skills/.claude/skills/` 提交 Git

---

## 输出格式

- Bug 分析报告: `reports/bug-analysis/*.json`
- 适配 Agent 报告: `reports/adapt-agent/` 与 `/tahp/reports`
- AI 自检报告: `reports/self-check/`
