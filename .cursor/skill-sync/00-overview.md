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
| **内容型** | 仅 SKILL.md | 草稿审核 → 写权威（P3 起审后 Git 直推） | Phase 1 起可 sync；P3 补齐审后落 Git |
| **包型** | 含 scripts/references 等 | Phase 2 已托管全量包；**仍直发** | Phase 3 改为待审 + 审后发布 + Git |

证据（演进）：

- P1：内容型 pull 以 SKILL.md 为主；草稿激活只写 `SKILL.md`
- P2：整包 hash / ZIP；本机 publish 仍**直接**写入中心 live（缺口 → P3 闸门）
- P3：待审 → 审后写 `data/` + Git 直推 + 主仓镜像；客户端可查 history

## 3. 目标架构

```
本机提交 → 中心 pending_review → 审核通过
  → 写入 easyadapter_bff/data/...
  → git commit + push master（CI 账号）
  → 镜像同步到主仓 easyadapter（skills / knowledge-base）
  → manifest 对同事可见
           │
           ▼ pull / 手动同步
tahp-console（本机）
  ├── Skill 同步中心 UI（含单 Skill Git 历史）
  ├── sync-status / sync / reinject
  ├── skills/.claude/skills/（工程副本）
  └── skill-injector 热注入 → Hermes runtime
```

### 角色边界

| 组件 | 职责 |
|------|------|
| easyadapter_bff | 权威 `data/...`、审核、Bundle、全量包、审后 Git 直推、审计 |
| easyadapter 主仓 | 镜像接收已发布 skills/kb；同事工程与 Git 历史对齐 |
| easyadapter/tahp-console | 本地执行、提交待审、同步 UI、历史查看、热注入 |
| GitLab | **版本与审计源**（commit history）；不做自研版本仓 |

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
| synced | 与中心**已发布**一致 |
| behind | 中心已发布有更新 |
| ahead | 本地有未提交修改（Phase 4） |
| local_only | 仅本机 |
| submitted_pending | 已提交中心、仍待审（Phase 3） |
| rejected | 最近提交被驳回（Phase 3） |
| conflict | 双方均改（Phase 4） |

本机状态文件：`{projectRoot}/.tahp/skill-sync-state.json`（不入 Git）。

## 5. 用户心智模型（目标）

> **改 Skill / 知识 → 提交中心（待审）→ 审核通过（写 data + 推 GitLab + 镜像主仓）→ 同步中心点一下 → 应用到 Agent**  
> **版本**：在客户端查看该 Skill 的 GitLab 历史；回滚用 Git revert / 再提审。

## 6. 阶段总览

| Phase | 目标 | 双仓 |
|-------|------|------|
| **1** | 可感知同步 + 免重启热注入（内容型） | 客户端主改；中心 manifest 向前兼容 |
| **2** | 包型全量托管与分发（提交仍直发） | 双仓同改 |
| **3** | 审核闸门 + 审后 Git 直推/主仓镜像 + 历史 UI + Bundle | 双仓同改 |
| **4** | ahead/conflict、审计加强、文档 SOP | 双仓同改 |

## 7. 中心部署约定

- 生产示例：`http://10.205.0.65:8660/`
- 配置：`TAHP_CENTRAL_URL` + `TAHP_CENTRAL_TOKEN`（见 `tahp-console/.env`）
- **禁止**在代码中硬编码中心 URL

## 8. 非目标（明确不做）

- 自研多版本 blob 仓 / current_version 指针（版本交给 GitLab）
- 审核通过后再开 MR（P3 定稿为 **直推 master**）
- 用纯 npm 私有包替代中心分发
- Phase 1 就做完整包上传
- 同时大改 `hermes-agent-main/`
- 提交 `.env` / 凭据 / 本机 sync-state / CI 私钥

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
