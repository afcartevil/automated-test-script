# Skill 同步管理 — 总体设计（定稿）

> 与 [README.md](./README.md) 配套。执行细节以各 `PHASE-*.md` 为准。

## 1. 问题陈述

同事将 Skill 导入工程目录后，需要：

- **单 Skill 更新**：改完后如何让他人本地对齐
- **业务多 Skill 同步更新**：同一业务相关多个 Skill 如何成组更新
- **可感知 + 可生效**：知道有没有更新、更新后 Agent 是否立即用到新版本

## 2. 现状诊断（2026-07 基线）

### 2.1 三层存储

| 层级 | 位置 | 角色 |
|------|------|------|
| 中心权威 | `easyadapter_bff/data/skills/.claude/skills/` | 审核发布源 |
| 工程副本 | `easyadapter/skills/.claude/skills/` | 本机完整包 |
| 运行时 | `%LOCALAPPDATA%/hermes/.../skills/` | Agent 实际加载 |

### 2.2 现有通道与缺陷

| 通道 | 缺陷 |
|------|------|
| 路径/ZIP 导入 | 适合首次；无「业务包」；无更新感知 |
| 知识库草稿审核 | 主要写 SKILL.md；与包型不同步 |
| 中心定时 pull（5min） | **仅同步 SKILL.md**；无 UI；无热注入 |
| Hermes 注入 | **仅 BFF 启动时**；import/pull 后不自动生效 |
| Git | 非研发门槛高；与中心审核双线 |

### 2.3 关键复核：两类 Skill

| 类型 | 特征 | 中心现状 | 完整分发 |
|------|------|----------|----------|
| **内容型** | 仅 SKILL.md | 草稿审核激活后可 pull | Phase 1 即可体验闭环 |
| **包型** | 含 scripts/references 等 | **中心目前不存附件** | 必须 Phase 2 托管全量包 |

证据：

- `easyadapter_bff` `activateSkillFromDraft()` 只写 `SKILL.md`
- sync pull 只回传 `{ id, rel_path, content }`
- 本地 `applyPull()` 只写 `skillsDir/<id>/SKILL.md`

## 3. 目标架构

```
easyadapter_bff（权威）
  ├── 内容型：草稿审核 → SKILL.md
  ├── 包型：完整包上传/托管（Phase 2）
  ├── Bundle 注册表（Phase 3）
  └── sync manifest（hash + files + bundle_ids）
           │
           ▼ pull / 手动同步
tahp-console（本机）
  ├── Skill 同步中心 UI
  ├── sync-status / sync / reinject
  ├── skills/.claude/skills/（工程副本）
  └── skill-injector 热注入 → Hermes runtime
```

### 角色边界

| 组件 | 职责 |
|------|------|
| easyadapter_bff | 权威源、审核、Bundle、全量包、审计 |
| easyadapter/tahp-console | 本地执行、同步 UI、热注入 |
| Git | 开发协作/备份；**不是**团队发布唯一通道 |

## 4. 核心概念

### 4.1 Skill Bundle

中心权威：`data/.tahp/skill-bundles.json`

- 显式 `bundles[]` + `auto_rules[]`（func_type+module / id_prefix）
- 本地只读缓存随 pull 下发

### 4.2 Skill Package

整目录 hash + file-level hash；小包内联 / 大包 URL；增量按文件拉。

### 4.3 对齐状态

| state | 含义 |
|-------|------|
| synced | 与中心一致 |
| behind | 中心有更新 |
| ahead | 本地有未提交修改（Phase 4） |
| local_only | 仅本机 |
| conflict | 双方均改（Phase 4） |

本机状态文件：`{projectRoot}/.tahp/skill-sync-state.json`（不入 Git）。

## 5. 用户心智模型（目标）

> **改 Skill → 中心审核 → 同步中心点一下 → 应用到 Agent**

## 6. 阶段总览

| Phase | 目标 | 双仓 |
|-------|------|------|
| **1** | 可感知同步 + 免重启热注入（内容型） | 客户端主改；中心 manifest 向前兼容 |
| **2** | 包型全量托管与分发 | 双仓同改 |
| **3** | Bundle CRUD + 按包同步 | 双仓同改 |
| **4** | ahead/conflict、审计、文档 SOP | 双仓同改 |

## 7. 中心部署约定

- 生产示例：`http://10.205.0.65:8660/`
- 配置：`TAHP_CENTRAL_URL` + `TAHP_CENTRAL_TOKEN`（见 `tahp-console/.env`）
- **禁止**在代码中硬编码中心 URL

## 8. 非目标（明确不做）

- 用纯 Git / npm 私有包替代中心分发
- Phase 1 就做完整包上传
- 同时大改 `hermes-agent-main/`
- 提交 `.env` / 凭据 / 本机 sync-state

## 9. 相关代码锚点

| 用途 | 路径 |
|------|------|
| 本地 pull | `tahp-console/packages/server/src/services/tahp/sync/pull.ts` |
| 本地 scheduler | `.../sync/scheduler.ts` |
| 本地 central client | `.../sync/central-client.ts` |
| 契约类型 | `.../sync/manifest.ts`（须与中心一致） |
| Hermes 注入 | `.../services/hermes/skill-injector.ts` |
| Skills UI | `.../client/src/views/hermes/SkillsView.vue` |
| 中心 sync | `easyadapter_bff/src/routes/sync.ts` |
| 中心 skills 扫描 | `easyadapter_bff/src/services/skills.ts` |
| 中心激活 | `easyadapter_bff/src/services/skill-drafts.ts` |
