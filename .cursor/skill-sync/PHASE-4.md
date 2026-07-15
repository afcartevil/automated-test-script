# Phase 4 — 状态补齐与 SOP（精简可执行提案）

> **状态**：代码已落地（Step 4A–4C）；待环境冒烟后勾选 4D。  
> **前置**：Phase 1–3 主路径稳定（审核闸门 + sync/注入 + 历史/Bundle）。  
> **自检**：每 Step 结束遵守 [SELF-CHECK.md](./SELF-CHECK.md)。  
> **范围红线**：**只做**本机「待审 / 驳回」状态 + 文档 SOP；**不做** ahead/conflict、审计报表增强。

---

## 1. 为什么还要有 Phase 4

P3 审核闸门已通，但本机同步中心状态机仍只有：

`synced | behind | local_only | unknown`

结果：提交服务器成功后仍显示「仅本机」，驳回后无原因展示。  
中心侧已有 `GET .../submission/latest`，客户端 `centralClient.latestSkillSubmission` 也已存在，**差的是 status 接入 + UI 徽章**。

本 Phase **只补这一缺口 + 写清使用 SOP**，避免再做治理大功能导致过度修改与 performance 回退。

---

## 2. 交付目标（最小集）

1. 本机新增状态：
   - `submitted_pending`：最近一次整包提交仍为 `pending_review`
   - `rejected`：最近一次整包提交为 `rejected`（展示驳回原因）
2. SyncCenter：对应徽章 / 文案；待审隐藏「提交服务器」；拒审可再提。
3. 文档 SOP：发布走中心；import = 离线/首次兜底；状态速查表。

### 明确不做

| 项 | 原因 |
|----|------|
| `ahead` / `conflict` + 基线 hash | 场景少；误判与性能风险大 |
| 「覆盖为中心版」特化流程 | 沿用现有 sync / 单 Skill 拉取即可 |
| 中心审计筛选 / CSV 导出 | 与主路径无关；现有审计日志已够用 |
| WebSocket 推送 / git status 判 ahead | 非本 Phase 目标 |

---

## 3. 状态判定（仅 submission 覆盖）

输入：

| 记号 | 含义 | 来源 |
|------|------|------|
| `L` | 本地整包 hash | `getLocalPackageHash`（沿用指纹缓存） |
| `C` | 中心已发布 hash | manifest |
| `S` | 最近一次提交 | `latestSkillSubmission(id)` |

在现有基础态算完后，**仅对非 `synced`（或仍可能提交的行）**按需查 `S`，再覆盖：

| 优先 | 条件 | state |
|------|------|-------|
| 1 | `S.status === 'pending_review'` | `submitted_pending` |
| 2 | `S.status === 'rejected'` 且（无 `S.hash` 或 `L === S.hash`） | `rejected`（附 `S.comment`） |
| 3 | 否则 | 保持原基础态（`synced` / `behind` / `local_only` / `unknown`） |

说明：

- **不引入基线 `B`**，不实现 ahead/conflict。
- `synced` 一般可跳过 latest 查询（减少中心请求）；若哈希已对齐仍有 pending 属异常，可不特殊处理。
- 查询失败：**降级为原基础态**，不阻塞列表、不抛错打断整页。
- 复用现有 status TTL / 磁盘快照（P3 已做），禁止为新状态做全量重扫。

---

## 4. UI（SyncCenter + i18n）

| 状态 | 徽章 | 提交按钮 | 额外信息 |
|------|------|----------|----------|
| `submitted_pending` | 待审核（蓝/琥珀） | 隐藏 | 可显示 submit_id（可选） |
| `rejected` | 已拒绝（红） | 显示「重新提交」 | tooltip / 行内展示 `comment` |

顶部 banner：若存在 pending / rejected，一句提示即可（不必大改布局）。

---

## 5. API

**无新接口。** 复用：

- `GET /api/tahp/sync/skill/:id/submission/latest`（中心，P3）
- 本机 `centralClient.latestSkillSubmission`

可选优化（仍算本 Phase，≤1 个小函数）：批量接口缺省时用 `Promise.all` 有上限并发（如 6），失败单条忽略。

---

## 6. 影响文件清单（必须改，建议 ≤6）

### 6.1 easyadapter / tahp-console

| # | 文件 | 动作 |
|---|------|------|
| 1 | `packages/server/src/services/tahp/sync/status.ts` | 扩展 `SkillSyncStateName`；按需拉 latest 覆盖 pending/rejected；附 `reject_reason?` |
| 2 | `packages/client/src/components/hermes/skills/SkillSyncCenter.vue` | 徽章 / 按钮 / 原因展示 |
| 3 | `packages/client/src/i18n/locales/zh.ts` / `en.ts` | 文案 |
| 4 | `tests/server/skill-sync-status.test.ts` | pending / rejected 覆盖用例（可增量） |

### 6.2 文档

| # | 文件 | 动作 |
|---|------|------|
| 1 | `.cursor/skill-sync/PHASE-4.md` | 本文 |
| 2 | `.cursor/skill-sync/README.md` | 进度与变更记录 |
| 3 | `.cursor/rules/tahp-skills-hermes.mdc` | 补 SOP：发布走中心；import 兜底；状态含待审/驳回 |
| 4 | `00-overview.md`（小改） | 标明 ahead/conflict **暂缓**，不写「P4 必做」 |

中心仓 `easyadapter_bff`：**本 Phase 默认零代码改动**（接口已有）。若测发现 latest 契约缺字段再单开补充，不得默默扩大范围。

---

## 7. 执行顺序（Step）

| Step | 仓 | 工作 | 验收 |
|------|-----|------|------|
| **4A** | client | `status.ts` 接入 latest → `submitted_pending` / `rejected` + 单测 | 提交后列表变待审；驳回见原因；synced/behind 不回归；加载仍走缓存，无整页长扫 |
| **4B** | client | SyncCenter + i18n | 待审隐藏提交；拒审可再提 |
| **4C** | 文档 | rules + overview/README 收敛 | SOP 与实现对齐 |
| **4D** | client | `npm test`（相关）+ `npm run build` + SELF-CHECK | 自检报告通过 |

---

## 8. 性能约束（强制）

1. 禁止因本 Phase 去掉或绕过 hash/status 缓存。  
2. `latestSkillSubmission`：**按需**、可并发、可失败降级；禁止「每个 skill 串行阻塞」。  
3. 首次进入仍应能先出缓存快照，再在后台刷新状态（沿用 Pinia + `cached=1`）。

若实现后同步中心再次出现固定长加载，视为本 Phase **验收失败**。

---

## 9. 风险与缓解

| 风险 | 缓解 |
|------|------|
| latest 拖慢 status | 只查候选行 + 并发上限 + TTL |
| 中心未配置 / 断连 | 不覆盖，保持 local_only/behind |
| 驳回后用户又改了本地 | `L !== S.hash` 时不强制显示 rejected（回 behind/local_only，可再提） |
| 文档写冒了 ahead/conflict | overview 标明暂缓；本文范围红线 |

---

## 10. 验收清单

1. 提交整包成功 → 该行立即（或刷新后）为 **待审核**，无「提交服务器」。  
2. 中心驳回并填原因 → 本机为 **已拒绝**，可见原因；可再提。  
3. 审核通过并 sync → **已同步**（或 behind→同步后 synced），不卡住待审。  
4. 已对齐的大量 synced Skill **不因**本改动拖慢进页。  
5. build / 相关测试通过；SELF-CHECK 勾选；无规划外文件。

---

## 11. 已锁定决策（2026-07-15）

| # | 项 | 结论 |
|---|-----|------|
| 1 | 范围 | **仅** pending/rejected + 文档 |
| 2 | ahead/conflict | **砍掉**（暂缓，不进本 Phase） |
| 3 | 审计报表 | **砍掉** |
| 4 | 基线 hash | **不做** |
| 5 | 中心仓代码 | **默认不动** |

---

## 12. 开工

确认本精简稿后按 **4A → 4B → 4C → 4D** 实现；单批文件 ≤6，超出先改本文。
