# Phase 2 — 包型 Skill 全量分发（大纲）

> **状态**：大纲。须在 Phase 1 验收通过后，细化为「可执行提案」并更新本文，再开发。  
> **目标**：中心托管并下发含 `scripts/`、`references/` 等的完整 Skill 包。  
> **自检**：细化与开发均须遵守 [SELF-CHECK.md](./SELF-CHECK.md)。

## 1. 交付目标

1. 中心可上传/存储完整 skill 目录（不仅 SKILL.md）。
2. manifest 含 file-level hash；pull 对包型返回 `package_url` 或内联 archive。
3. 本地 `applyPull` 解压覆盖工程副本 → 热注入。
4. `requirements.txt` 变更时前端提示 `npm run setup`。

## 2. 预估必须改（细化时锁定）

### easyadapter_bff

- `src/services/skill-package.ts`（新）：打包/解包/hash
- `src/routes/skills.ts` 或新路由：`POST /api/tahp/skills/:id/package`
- `src/routes/sync.ts`：pull 扩展、`GET /api/tahp/sync/skill/:id/package`
- `src/services/skills.ts`：目录级扫描
- smoke-test

### easyadapter

- `sync/manifest.ts`：契约对齐
- `sync/central-client.ts`：拉 package
- `sync/pull.ts`：解压应用
- `sync/status.ts`：整包 hash 比对
- UI：同步结果提示 deps
- 测试

## 3. 待细化项（Phase 1 后补全）

- [ ] tar.gz 体积阈值（内联 vs URL）
- [ ] 上传鉴权（admin only）
- [ ] 本地「发布包到中心」是否做
- [ ] 文件级增量 vs 整包替换策略
- [ ] 可执行提案：精确文件列表、API 样例、验收清单

## 4. 依赖

- Phase 1：sync-status / reinject / UI / manifest `files[]` 字段已存在
