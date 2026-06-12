# TAHP — Claude Code 配置

## 项目

TECNO AI Harness Platform (TAHP) — 传音 Android 底软集成部 AI 辅助开发平台。

## 首先阅读

执行任何任务前，必须先阅读 [AGENTS.md](AGENTS.md) 了解项目导航。

---

## 架构分层

```
tahp-console (Vue + Koa BFF :8650)
    │
    ├── Hermes Agent Bridge ── hermes-agent-main/
    ├── TaskStream (Socket.IO /tahp-run)
    ├── knowledge-base/ (BFF 自管 + BM25)
    └── reports/
    │
    ▼
skills/.claude/skills/  ← 业务规则与执行 Skill
```

**生产路径**：智能诊断、AI 适配调试、知识库、报告均通过 Console BFF 直接驱动 Hermes Agent，不再经过 MCP stdio 桥。

---

## 核心规则

1. **Skill 优先**：业务规则写在 `skills/` 对应 SKILL.md 中
2. **防幻觉**：所有代码产出必须有据可查，禁止编造
3. **最小变更**：只修改与任务直接相关的代码
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

# Pre-commit（可选）
powershell -File scripts/pre-commit-check.ps1
```

---

## tahp-console 可视化控制台

```bash
cd tahp-console
npm install
npm run setup          # 检查 Python 3 + hermes-agent venv

npm run dev            # client:5173, server:8650
npm run build && npm run start
```

环境变量（`.env` 或 shell export）：

- `TAHP_PROJECT_ROOT` — TAHP 主仓目录，默认自动探测（含 `skills/.claude/skills` 或 `knowledge-base/`）
- `TAHP_PYTHON` — Python 可执行路径
- `PORT` — 端口，默认 8650
- `AUTH_DISABLED=1` — 默认开启内网免鉴权

控制台面板：仪表盘 / 智能诊断 / AI 适配调试 / 知识库 / 报告 / Skills 库 / 对话

### 如何新增 Skill

在 `skills/.claude/skills/<skill-name>/` 下创建 `SKILL.md`，并在 Console Skills 库或 Agent 配置中引用。

---

## 文件操作范围

- 可操作: `skills/`, `knowledge-base/`, `tahp-console/`, `scripts/`, `docs/`, `reports/`
- 禁止: `.git/`, `.env`, 无关第三方子模块的大范围改动

---

## 输出格式

- Bug 分析报告: 落盘 `reports/bug-analysis/*.json`
- 适配 Agent 报告: 落盘 `reports/adapt-agent/` 与 `/tahp/reports` 浏览
