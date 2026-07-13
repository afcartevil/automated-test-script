# Phase 3 — Bundle 管理（大纲）

> **状态**：大纲。须在 Phase 2 验收后细化。  
> **目标**：业务级「Skill 包」定义、发布与按包同步。  
> **自检**：须遵守 [SELF-CHECK.md](./SELF-CHECK.md)。

## 1. 交付目标

1. 中心维护 `data/.tahp/skill-bundles.json`（权威）。
2. 显式 bundles + auto_rules（func_type+module / id_prefix）。
3. 中心后台 Bundle CRUD UI。
4. 本地 sync-status/sync 支持 `bundle_id`；同步中心「同步此包」打通正式 Bundle。
5. 本地只读缓存 `.tahp/skill-bundles.cache.json`。

## 2. 预估必须改（细化时锁定）

### easyadapter_bff

- Bundle 服务 + `GET/PUT /api/tahp/skill-bundles*`
- `POST .../publish`（审计）
- client `SkillsView` 旁 Bundle 管理页
- manifest `bundle_ids` 由空数组变为真实归属

### easyadapter

- status/sync 按 bundle 过滤
- SkillSyncCenter 用正式 Bundle 替代 P1 的 func_type 临时分组
- 测试 + i18n

## 3. 待细化项

- [ ] auto_rules 与显式冲突时优先级
- [ ] 是否允许一 skill 多 bundle
- [ ] 可执行提案落盘

## 4. 依赖

- Phase 1 UI 骨架、Phase 2 全量包（业务包常含脚本）
