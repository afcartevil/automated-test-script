# Phase 1 — 可感知同步 + 免重启热注入（可执行提案）

> **状态**：代码已实现，待手工冒烟确认  
> **前置**：阅读 [00-overview.md](./00-overview.md) + [SELF-CHECK.md](./SELF-CHECK.md)  
> **范围**：内容型 Skill（SKILL.md）；不含包型附件、不含 Bundle CRUD  
> **中心**：`http://10.205.0.65:8660/`（经环境变量，不硬编码）  
> **自检**：每个 Step 与整 Phase 结束后必须按 SELF-CHECK 出具自检报告，未通过不得进入下一步  
> **文档路径**：`.cursor/skill-sync/`（权威；勿用被 gitignore 匹配的任意 `docs/` 路径）

---

## 1. 交付目标

1. 本机 Console 能展示：中心是否连通、哪些 Skill 落后、按分组查看。
2. 一键同步（触发 pull）内容型 Skill。
3. pull / 手动同步后 **无需重启 BFF**，可热注入 Hermes。
4. 中心 manifest 增加向前兼容字段，为 P2/P3 铺路。

**验收通过后再开 Phase 2。**

---

## 2. 任务边界

| 项 | 内容 |
|----|------|
| 功能域 | Console UI + 本地 sync API + Hermes 热注入；中心契约对齐 |
| 不做 | 包上传、file 级增量包、Bundle 管理、ahead/conflict 精细态 |
| 变更控制 | 遵循 `00-change-control`；双仓同批改契约 |

---

## 3. 影响文件清单

### 3.1 必须改 — easyadapter（客户端）

| # | 文件 | 动作 | 说明 |
|---|------|------|------|
| 1 | `tahp-console/packages/server/src/services/tahp/sync/hash.ts` | **新** | `shortHash` = sha256 前 16，与中心一致 |
| 2 | `tahp-console/packages/server/src/services/tahp/sync/status.ts` | **新** | manifest 比对、读写 sync-state |
| 3 | `tahp-console/packages/server/src/services/tahp/sync/manifest.ts` | **改** | 类型增加可选 `bundle_ids`、`files` |
| 4 | `tahp-console/packages/server/src/services/tahp/sync/pull.ts` | **改** | applyPull 后对变更 skill 热注入 |
| 5 | `tahp-console/packages/server/src/services/tahp/sync/index.ts` | **改** | 导出 status 等 |
| 6 | `tahp-console/packages/server/src/services/hermes/skill-injector.ts` | **改** | `injectMissingSkills(skillIds?: string[])` + 进程内 mutex |
| 7 | `tahp-console/packages/server/src/routes/tahp/skill-sync.ts` | **新** | 3 个 API |
| 8 | `tahp-console/packages/server/src/routes/tahp/index.ts` | **改** | 挂载 skill-sync |
| 9 | `tahp-console/packages/client/src/api/hermes/skills.ts` | **改** | fetchSyncStatus / triggerSync / reinject |
| 10 | `tahp-console/packages/client/src/components/hermes/skills/SkillSyncCenter.vue` | **新** | 同步中心 UI |
| 11 | `tahp-console/packages/client/src/views/hermes/SkillsView.vue` | **改** | Tab：库浏览 \| 同步中心；import 降权文案 |
| 12 | `tahp-console/packages/client/src/i18n/locales/zh.ts` | **改** | 文案 |
| 13 | `tahp-console/packages/client/src/i18n/locales/en.ts` | **改** | 文案 |
| 14 | `tahp-console/tests/server/skill-sync-status.test.ts` | **新** | status/hash 单测 |
| 15 | `tahp-console/tests/server/skill-injector.test.ts` | **改** | skillIds 过滤用例；路径解析 mock `hasTahpProject` |
| 16 | `.cursor/skill-sync/*` | **文档** | 执行文档权威位置 |

### 3.2 必须改 — easyadapter_bff（中心）

| # | 文件 | 动作 | 说明 |
|---|------|------|------|
| 1 | `src/routes/sync.ts` | **改** | manifest skill 项增加 `bundle_ids: []`、`files: [{rel_path,hash,size}]` |
| 2 | `scripts/smoke-test.ts` | **改**（若断言 manifest 结构） | 兼容新字段 |

### 3.3 可能受影响（本批不改业务逻辑）

- `scheduler.ts` — 仍定时 pull；受益于 pull 后自动 reinject
- 知识库草稿 / import — 路径不变

### 3.4 不受影响

- `required-skills.json`、skill-config、包型附件、Git 流程

---

## 4. API 契约

### 4.1 本机新增

```
GET /api/tahp/skills/sync-status
→ {
  configured: boolean,
  central_url: string | null,
  connected: boolean,
  last_pulled_at: string | null,
  behind_count: number,
  skills: Array<{
    id: string,
    state: 'synced' | 'behind' | 'local_only' | 'unknown',
    central_hash?: string,
    local_hash?: string,
    updated_at?: string,
    bundle_ids: string[],
    name?: string,
    func_type?: string,
    module?: string
  }>,
  groups: Array<{
    id: string,
    label: string,
    behind_count: number,
    skill_ids: string[]
  }>
}

POST /api/tahp/skills/sync
body: { skill_ids?: string[] }
→ {
  pull: { entries, skills, configs, generated_at },
  reinjected: string[],
  reinject_error?: string,
  status: { behind_count, last_pulled_at, ...精简 }
}

POST /api/tahp/skills/reinject
body: { skill_ids?: string[] }
→ { injected, updated, skipped, sourceDir, targetDir }
```

说明：

- 中心未配置：`configured: false`，不抛 500。
- ping 失败：`configured: true, connected: false`。
- P1 的 `groups`：按本地/中心 `func_type`（缺省「未分类」）聚合，**非正式 Bundle**（正式 Bundle 见 Phase 3）。
- P1 不同步实现 `ahead` / `conflict` 精细判定（字段可预留，逻辑 P4）。

### 4.2 中心 manifest 扩展（向前兼容）

每个 `type: 'skill'` 项增加：

```ts
{
  // ...既有 id, updated_at, hash, status
  bundle_ids: [],  // P1 恒为空数组
  files: [
    { rel_path: 'SKILL.md', hash: string /* 同 item.hash */, size: number }
  ]
}
```

旧客户端忽略未知字段；新客户端可读。

### 4.3 Hash 算法（双仓必须一致）

```
shortHash(content) = sha256(utf8).hex.slice(0, 16)
```

中心现有：`easyadapter_bff/src/services/hash.ts`  
本地新建：`sync/hash.ts`（勿用 md5）。

---

## 5. 状态判定规则（P1）

| 条件 | state |
|------|-------|
| 中心有且本地无，或 local_hash ≠ central_hash | `behind` |
| 中心有且 hash 相等 | `synced` |
| 本地有、中心无 | `local_only` |
| 无法读本地文件 | `unknown` |

本机状态持久化：`{projectRoot}/.tahp/skill-sync-state.json`（gitignore 已有 `.tahp/` 则遵循；勿提交）。

---

## 6. 实现要点

### 6.1 status.ts

1. `isCentralConfigured()` 否 → 直接返回 disabled。
2. `centralClient.ping()` + `manifest()`。
3. 扫描 `tahpPaths.skillsDir` 下各 skill 的 `SKILL.md`，算 local_hash。
4. 合并生成 skills[] + groups[]；写 sync-state。

### 6.2 skill-injector

1. `injectMissingSkills(skillIds?: string[])`：若传入数组，只处理这些目录名。
2. 进程内 mutex，避免与 bootstrap / sync 并发写。
3. 签名比较逻辑保持现有（path+size+mtime）。

### 6.3 pull.ts

1. `applyPull` 统计本次写入的 skill ids。
2. try/catch 调用 injector（失败不阻断 pull，记录 `reinject_error`）。
3. 更新 last_pulled_at（可与 status 共用 state 文件）。

### 6.4 路由

- 新建 `routes/tahp/skill-sync.ts`，在 `routes/tahp/index.ts` **先于或并列**挂载（路径无与 `:skillId` GET 冲突；DELETE `:skillId` 在 skills.ts，注意勿把 `sync` 当成 skillId——当前仅 DELETE 有 param，GET/POST 新路径安全）。

### 6.5 UI SkillSyncCenter

- 顶部：连接状态、上次同步、落后数、`[立即检查]` `[同步全部]`
- 列表：按 groups 展示，落后徽章
- 完成后弹窗：更新数 + `[应用到 Agent]`（调 reinject）
- 未配置中心：引导配置 `TAHP_CENTRAL_URL` / `TAHP_CENTRAL_TOKEN`
- SkillsView：Tab「库浏览」「同步中心」；原 import 按钮文案改为「高级 / 首次导入」类表述（i18n）

---

## 7. 执行顺序（严格按序）

| Step | 仓 | 工作 | 验证 |
|------|-----|------|------|
| 1 | bff | manifest 扩展 + smoke（如需） | 中心可启；GET manifest 含新字段 |
| 2 | client | hash.ts + status.ts + 单测 | `npm test` 相关 |
| 3 | client | injector 过滤 + mutex + 单测 | `npm test` skill-injector |
| 4 | client | pull 后 reinject + skill-sync 路由 | `npm test` |
| 5 | client | SkillSyncCenter + SkillsView Tab + i18n | `npm run build` |
| 6 | 联调 | 对 `10.205.0.65:8660` ping / sync-status / sync | 手工冒烟清单见下 |

---

## 8. 验证清单

### 自动

```bash
cd E:/TAHP/easyadapter/tahp-console
npm test
npm run build
```

中心（如有 smoke）：

```bash
cd E:/TAHP/easyadapter_bff
npm run smoke
```

### 手工冒烟

1. `.env` 已配 `TAHP_CENTRAL_URL=http://10.205.0.65:8660` 与 TOKEN。
2. 打开 `/hermes/skills` → **同步中心**：显示已连接。
3. 点「立即检查」：列表有状态徽章。
4. 点「同步全部」：返回成功；若有 behind 应变少。
5. 点「应用到 Agent」或依赖自动 reinject：无需重启 BFF。
6. 临时去掉 TOKEN/URL：同步中心显示未配置引导，不白屏。
7. 库浏览 Tab / 原 import 仍可用。

---

## 9. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 热注入并发 | injector mutex |
| reinject 失败 | 不阻断 pull；UI 提示可重试 |
| hash 不一致假 behind | 统一 shortHash |
| 双仓漏改 | Step 1 与 Step 2–5 同批次；manifest 注释互指路径 |
| 文件数 >8 | 允许；按 Step 拆 commit，但同一交付批次 |

---

## 10. 回滚

- 关闭/清空 `TAHP_CENTRAL_URL` 即回到无同步 UI 引导态。
- 新路由与新组件为增量；回滚可 revert 本 Phase 相关 commit。
- 中心新字段为加字段，旧客户端兼容。

---

## 11. 完工定义（DoD）

- [ ] 上表「必须改」文件均已按本文实现，无顺手重构
- [ ] `npm test` + `npm run build` 通过（零 fail）
- [ ] 手工冒烟 1–7 通过
- [ ] [SELF-CHECK.md](./SELF-CHECK.md) 全文清单已勾选，并向用户输出「自检报告」
- [ ] 若有规划外修改：已说明原因/必要性，且已回写本文文件清单
- [ ] [README.md](./README.md) 进度更新为 Phase 1 完成
- [ ] **未**开始 Phase 2 代码，除非另开提案并确认

---

## 12. Step 级自检（每步结束必做）

每个 Step 结束后：

1. `git status` + `git diff --name-only` 对照本文 §3 清单  
2. 跑该 Step「验证」列命令，确保无报错  
3. 回复中附简版自检报告（实际文件 / 与规划差异 / 验证结果）  
4. 有规划外改动 → 停手，走 SELF-CHECK §3，不得静默带过  

---

## 13. 开工口令

用户确认原文案：

> **确认，开始 Phase 1**

确认后从 **Step 1（bff manifest）** 开始，每完成一步勾选进度并出具自检报告；若实现偏离本文，先改文档再改代码。
