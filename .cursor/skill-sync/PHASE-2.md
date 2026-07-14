# Phase 2 — 包型 Skill 全量分发（可执行提案）

> **状态**：自检通过并已推送（2026-07-14）  
> **前置**：Phase 1 已交付；遵守 [SELF-CHECK.md](./SELF-CHECK.md)  
> **目标**：中心托管完整 Skill 目录；本机按包同步并热注入  
> **文档路径**：`.cursor/skill-sync/`

---

## 1. 交付目标

1. 中心扫描/存储 skill **整目录**（SKILL.md + scripts/references/…）。
2. manifest 使用 **整包 hash** + **file-level files[]**。
3. pull：小包内联文件；大包走 `package_url` 下 ZIP。
4. 本地 applyPull 覆盖目录 → 热注入；`requirements.txt` 变更时提示 `npm run setup`。
5. 本机可将工程内 skill **发布包到中心**（机器 token，便于联调）。

## 2. 锁定决策

| 项 | 定稿 |
|----|------|
| 归档格式 | **ZIP**（与 Console 已有 `adm-zip` 一致；中心新增依赖 `adm-zip`） |
| 内联阈值 | 未压缩合计 **≤ 1.5MB** → pull 内联 `files[]`；否则仅 `package_url` |
| 上传鉴权 | `POST .../package` 走 **central token**（本机发布）；后台 admin 上传同路径可选复用 |
| 本地发布 | **做**：`POST /api/tahp/skills/publish-package` |
| 同步策略 | **整包替换**（解压覆盖 skill 目录；不删未包含的本地多余文件以外的逻辑：先清空目标 skill 目录再解压） |
| 排除文件 | `.env`、`.env.*`、`node_modules`、`__pycache__`、`.git`、`*.pyc` |
| 整包 hash | 对 `files` 按 `rel_path` 排序后拼接 `rel_path\\0hash\\n`，再 `shortHash`；**manifest.item.hash = 整包 hash**（相对 P1 仅 SKILL.md hash 的升级） |

## 3. 影响文件清单

### 3.1 easyadapter_bff

| # | 文件 | 动作 |
|---|------|------|
| 1 | `src/services/skill-package.ts` | **新** 列文件/hash/打 ZIP/解 ZIP/读包 |
| 2 | `src/services/skills.ts` | **改** 可选暴露目录 mtime；list 仍基于 SKILL.md |
| 3 | `src/routes/sync.ts` | **改** manifest 整包 files；pull 扩展；`GET/POST /skill/:id/package` |
| 4 | `package.json` | **改** 依赖 `adm-zip` |
| 5 | `scripts/smoke-test.ts` | **改** 包上传/下载冒烟 |
| 6 | `docs/skill-sync/README.md` | **改** 指向 Phase 2 |

### 3.2 easyadapter（客户端）

| # | 文件 | 动作 |
|---|------|------|
| 1 | `sync/manifest.ts` | **改** PullPayload.skills 扩展字段 |
| 2 | `sync/skill-package.ts` | **新** 本地列文件/整包 hash/ZIP 应用（adm-zip） |
| 3 | `sync/status.ts` | **改** 用整包 hash 比对 |
| 4 | `sync/central-client.ts` | **改** pullPackage / uploadPackage |
| 5 | `sync/pull.ts` | **改** 应用内联 files 或下载 ZIP |
| 6 | `routes/tahp/skill-sync.ts` | **改** publish-package；sync 结果带 deps 提示 |
| 7 | `SkillSyncCenter.vue` + i18n | **改** requirements 提示；可选「发布到中心」 |
| 8 | `tests/server/skill-package-sync.test.ts` | **新** |

### 3.3 不做（P2）

- Bundle CRUD（P3）
- 文件级增量 patch（仅整包）
- 中心后台完整上传 UI（可用 API + 本机发布）

## 4. API 契约

### 4.1 Manifest skill 项

```ts
{
  type: 'skill', id, updated_at, status,
  hash: string,              // 整包 hash
  bundle_ids: [],
  files: Array<{ rel_path, hash, size }>,  // 全文件
  has_attachments: boolean   // files 不止 SKILL.md
}
```

### 4.2 Pull skills[] 项

```ts
{
  id, rel_path, updated_at,
  content: string,           // 仍带 SKILL.md 文本（兼容）
  hash: string,              // 整包 hash
  files?: Array<{ rel_path: string; content_b64: string; hash: string }>, // 小包
  package_url?: string,      // 大包，如 /api/tahp/sync/skill/:id/package
}
```

### 4.3 中心

```
GET  /api/tahp/sync/skill/:id/package   → application/zip（central token）
POST /api/tahp/sync/skill/:id/package   → body { archive_b64 } 解压写入权威目录
```

### 4.4 本机

```
POST /api/tahp/skills/publish-package  body: { skill_id }
→ { id, file_count, hash }

POST /api/tahp/skills/sync  响应增加
  requirements_changed: string[]  // skill ids
```

## 5. 执行顺序

| Step | 仓 | 工作 |
|------|-----|------|
| 1 | 文档 | 本文定稿；README 进度更新 |
| 2 | bff | skill-package 服务 + manifest/pull/package API + adm-zip |
| 3 | client | skill-package + status 整包 hash + pull 应用 |
| 4 | client | publish-package + UI 提示 |
| 5 | 双仓 | 单测 / build；自检报告 |

## 6. 验收

1. 中心 skill 目录含 `scripts/foo.py` 时，manifest.files 含该路径，hash≠仅 SKILL.md。
2. 本机 sync 后工程目录出现 scripts，并 reinject。
3. 改 requirements.txt 后 sync 响应/UI 提示 setup。
4. publish-package 可将本机 skill 推到本地中心。
5. 仅 SKILL.md 的内容型 skill 行为与 P1 兼容。

## 7. 风险

| 风险 | 缓解 |
|------|------|
| 大 ZIP 超时 | pull 下载 timeout 提升至 120s；阈值走 URL |
| 覆盖误删本地实验文件 | 仅覆盖目标 skill_id 目录；local_only 不强制删 |
| hash 算法漂移 | 双仓共用同一 list/hash 规则，单测锁定 |

## 8. 开工

用户已要求「完成规划和开发」→ 按本提案 Step 2 起执行。
