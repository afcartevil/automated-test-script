# 适配前置信息库 — 可执行实施方案

> **状态**：A1–A6 已落地（2026-07-16）；本文保留为实施方案与验收口径。
>
> **配套文档**：架构设计见 [`DESIGN-中心前置库.md`](./DESIGN-中心前置库.md)。本文只讲**怎么落地**：精确到文件、接口契约、权限中间件、交互流程、分步 PR 与验收命令。
>
> **决策基线（已默认拍板 §12）**：① 历史仅文件快照、不强绑 Git；② 每项目同时仅 1 个 `active` 战役；③ 克隆默认 `reuse_only`；④ V1 本机**只拉不推**；⑤ `from_os/to_os` 自由文本；⑥ 首期覆盖 `adapt-debug` 全域，FA/CC 预留。
>
> **三步工作流约束**：本文是「提案」。**未获确认前不写代码**。确认后按 §8 分步实现，每步先给文件级 diff 清单再落码。

> **本方案范围（重要）**
> - ✅ 在内：中心 BFF 前置库（存储/编辑/历史/Excel/拓展性）+ 用户端「**选择或输入项目 → 拉取该项目全部前置 → 自动填充前置表单**」。
> - ❌ 不在内：AI 适配的**启动与编排**（属既有手动操作）。用户端仅负责把前置信息拉回并填表，是否/何时启动适配由人工决定。

---

## 0. 全景（一图看懂数据流）

```text
                    ┌─────────────────────── 中心 easyadapter_bff（权威） ───────────────────────┐
业务/审核员 ──浏览器──▶ Web 后台「适配前置」页                                                     │
  (登录 Bearer)      │  requireReviewer 读写 / requireAdmin 删除                                   │
                    │        │                                                                    │
                    │        ▼  safeFileStore 原子写 + revision 乐观锁 + audit-log                 │
                    │  data/.tahp/adapt-prereqs/projects/{code}/campaigns/{cid}/domains/*.json     │
                    │        │  history/ 快照 + log.jsonl                                          │
                    │        ▼                                                                     │
本机 EasyAdapter ──▶ GET /api/tahp/sync/adapt-prereqs/resolve  (requireCentralToken, 只读)         │
  (x-tahp-token)    └──────────────────────────────────────────────────────────────────────────┘
       │
       ▼  合并进「AI 适配调试」表单（默认仅填空 + stale 黄标），人工确认后才跑
   tahp-console
```

**权限双通道**（复用现网机制，零新增鉴权体系）：

| 通道 | 中间件（现有） | 能力 |
|------|----------------|------|
| Web 后台 | `requireReviewer` / `requireAdmin` | 读写 / 删除 |
| 本机同步 | `requireCentralToken`（`x-tahp-token` + `x-tahp-actor`） | **只读** `resolve` |

---

## 1. 涉及仓库与文件总清单（提案预估）

> 规则要求「单批影响 ≤8 文件」。故下面按 §8 拆成多个 PR，每 PR 均 ≤8。此处先给**总视图**便于评估范围。

### 1.1 中心 `easyadapter_bff`（新增为主）

| 文件 | 动作 | 作用 |
|------|------|------|
| `src/paths.ts` | 改（+1 函数） | 新增 `adaptPrereqsDir()` 与目录创建 |
| `src/services/adapt-prereqs.ts` | 新增 | 存储/CRUD/克隆/历史 核心逻辑 |
| `src/services/adapt-prereqs-fields.ts` | 新增 | field 字典 + 分类规则（reusable/version_sensitive…） |
| `src/services/adapt-prereqs-xlsx.ts` | 新增 | Excel 导入导出（与模板同构） |
| `src/services/audit-log.ts` | 改（+action/type） | 追加 `adapt_prereq_*` 与 `target_type:'adapt_prereq'` |
| `src/routes/adapt-prereqs.ts` | 新增 | Web 侧 REST（reviewer/admin） |
| `src/routes/sync.ts` | 改（+1 只读路由） | `GET /adapt-prereqs/resolve` |
| `src/index.ts` | 改（注册路由） | 挂载 `adaptPrereqsRoutes` |
| `client/src/views/AdaptPrereqsView.vue` | 新增 | 后台编辑页 |
| `client/src/main.ts` | 改（+路由） | 注册 `/adapt-prereqs` |
| `client/src/App.vue` | 改（+导航） | 侧栏加「适配前置」 |
| `client/src/api.ts` | 改（+方法） | 前端 API 封装 |

### 1.2 本机 `tahp-console`（集成消费）

| 文件 | 动作 | 作用 |
|------|------|------|
| `packages/server/src/services/tahp/sync/central-client.ts` | 改（+方法） | `resolvePrereq()` |
| `packages/server/src/routes/tahp/*`（适配调试相关路由） | 改 | BFF 转发「从中心载入」 |
| `packages/client/src/**`（adapt-debug 页） | 改 | 「从中心载入前置」对话框 + stale 提示 |

> Console 侧精确文件在 §8 A6 步开工前，用 grep 复核后再定（避免现在加载无关文件）。

---

## 2. 存储契约（精确）

根目录：`adaptPrereqsDir()` = `<dataRoot>/.tahp/adapt-prereqs/`（与现有 `pendingPackagesDir()` 同级，默认不入 Git）。

```text
.tahp/adapt-prereqs/
  index.json                                  # { projects: [{code,name,product_line,active_campaign_id,updated_at}] }
  schema/
    base.json                                 # 系统基线字段（从 Console 域定义同步，只读基线）
    custom-global.json                        # 全局自定义（按 ws×domain；additions + overrides；admin 维护）
  projects/{project_code}/
    profile.json                              # 档案
    schema.custom.json                        # 项目级自定义（additions + overrides；reviewer 维护）
    campaigns/{campaign_id}/
      meta.json                               # from_os/to_os/status/based_on_campaign_id/...
      schema.custom.json                      # 战役/大版本级自定义（additions + overrides）
      domains/{workspace_id}__{domain_id}.json  # 当前权威值（含 revision）
      history/{workspace_id}__{domain_id}/
        r{revision}.json                      # 每次写入整包快照
        log.jsonl                             # 追加：actor/at/source/revision/changed_keys[]
```

> **值 vs 结构**：`domains/*.json` 只存**值**；字段的**结构**（有哪些字段、类型、选项、必填）由 `schema/*` 分层合并得到（见 §7 拓展性）。这样不同项目 / 大版本可以有不同前置项，而历史值不受结构变化破坏。
>
> **一致性**：`index.json` 仅为**列表缓存**，权威以各 `profile.json` 为准；写入后加锁重建，或启动/读取时按目录扫描惰性重建，避免与 profile 漂移。

### 2.1 键名与路径安全（强约束）

所有作为**文件名/路径片段**的标识符必须先过白名单正则，拒绝 `.`/`/`/`\`/空格，防目录穿越：

```ts
const SAFE_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/   // project_code / campaign_id / workspace_id / domain_id
```

- 不满足 → `400 非法标识符`，且**永不**用未校验字符串拼接 `join()`。
- 写文件统一走 `safeFileStore.writeText`（临时文件 + rename 原子落盘 + 单文件串行锁），杜绝并发半写。

### 2.2 域包 JSON schema（`adapt-debug__tp.json`）

```json
{
  "schema_version": 1,
  "project_code": "X6878-CN",
  "campaign_id": "a16-to-a17",
  "workspace_id": "adapt-debug",
  "domain_id": "tp",
  "revision": 12,
  "form_data": { "debug_project": "X6876_H786", "ic_vendor": "Goodix" },
  "field_meta": { "old_tp_firmware": { "category": "version_sensitive", "stale": true } },
  "updated_at": "2026-07-15T12:00:00Z",
  "updated_by": "zhangsan",
  "source": "ui"
}
```

- `revision` 单调递增，用于乐观锁。
- `field_meta[key].stale=true`：克隆升版后需人工更新的字段（路径类）。
- `source ∈ ui | excel | api | clone | restore`。

---

## 3. API 契约（逐条，含鉴权与错误码）

### 3.1 Web 侧 `src/routes/adapt-prereqs.ts`（`prefix: /api/tahp/adapt-prereqs`）

| 方法 | 路径 | 中间件 | 说明 | 主要错误 |
|------|------|--------|------|----------|
| GET | `/projects` | 无（读） | 项目列表摘要 | — |
| POST | `/projects` | `requireReviewer` | 建档案 `{code,name,product_line}` | 400 非法/409 已存在 |
| GET | `/projects/:code` | 无 | 档案 + campaigns[] | 404 |
| POST | `/projects/:code/campaigns` | `requireReviewer` | 建战役 `{campaign_id,from_os,to_os,based_on_campaign_id?,clone_mode?}` | 400/409 |
| PATCH | `/projects/:code/campaigns/:cid` | `requireReviewer` | 改 status/notes；设 active 时自动降级旧 active | 400/404 |
| GET | `/projects/:code/campaigns/:cid/domains` | 无 | 已填域列表 | 404 |
| GET | `/…/campaigns/:cid/domains/:ws/:domain/schema` | 无 | **生效 schema**（分层合并后的字段列表，Web/Excel/Console 共用） | 404 |
| POST | `/schema/custom` | **`requireAdmin`** | 全局自定义字段/覆盖（scope=global） | 400/409 |
| POST | `/projects/:code/schema/custom` | `requireReviewer` | 项目级自定义 | 400/409 |
| POST | `/…/campaigns/:cid/schema/custom` | `requireReviewer` | 战役级自定义 | 400/409 |
| PATCH/DELETE | `/…/schema/custom/:key` | 同作用域 | 改属性 / **弃用**（软删 `deprecated`，不物删） | 400/403/404 |
| POST | `/…/domains/:ws/:domain/fields/:key/options` | `requireReviewer` | 追加自定义下拉选项（回写字段字典） | 400/404 |
| GET | `/…/domains/:ws/:domain` | 无 | 当前 `form_data` + revision | 404 |
| PUT | `/…/domains/:ws/:domain` | `requireReviewer` | 整表覆盖；body 带 `revision` 乐观锁 | **409 版本冲突**（回传服务端当前版）/400 |
| GET | `/…/domains/:ws/:domain/history` | 无 | revision 列表 | 404 |
| GET | `/…/domains/:ws/:domain/history/:rev` | 无 | 某版快照 | 404 |
| POST | `/…/domains/:ws/:domain/restore` | `requireReviewer` | `{revision}` → 写为新版 | 400/404 |
| GET | `/…/campaigns/:cid/export.xlsx` | 无（读） | 导出 xlsx（`ctx.type='xlsx'` + `Buffer`；同构模板） | 404 |
| POST | `/…/campaigns/:cid/import` | `requireReviewer` | **JSON `{file_b64}`**（base64，与 skill 包 `archive_b64` 一致，无 multipart）；预览 diff、不落盘 | 400 解析失败 |
| POST | `/…/campaigns/:cid/import/commit` | `requireReviewer` | 确认写入（新 revision，按 schema 校验） | 400/409/422 |
| DELETE | `/projects/:code` | **`requireAdmin`** | 删档案（软删/归档优先） | 403/404 |
| DELETE | `/projects/:code/campaigns/:cid` | **`requireAdmin`** | 删战役 | 403/404 |

> **读接口是否要登录？** 建议：读接口不强制登录（与现有 `/knowledge` `entries` 读一致），但后台页面本身在登录后才可见（前端路由守卫）。若内网仍希望更严，可给读接口也加 `requireReviewer`——留作 §9 决策项。

### 3.2 用户端拉取侧（改 `src/routes/sync.ts`，**只读**）

用户端在 Console **选择或输入项目**后，一次性拉回该项目全部前置并自动填表。`syncRoutes` 已全局 `use(requireCentralToken)`，新增 3 条只读接口：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/tahp/sync/adapt-prereqs/projects` | 项目列表（供用户端下拉/搜索：`code/name/active_campaign_id`） |
| GET | `/api/tahp/sync/adapt-prereqs/resolve?project_code=&campaign_id=` | **整项目/整战役**：返回该战役**全部域**的 `form_data` + 生效 schema（自动填表所需）；`campaign_id` 省略取 active |
| GET | 同上 `&workspace_id=&domain_id=` | 可选：仅取单域（省流量） |

resolve 响应（**一次拿全，直接驱动自动填表**）：

```json
{
  "project_code": "X6850",
  "campaign_id": "a17-to-a18",
  "from_os": "17",
  "to_os": "18",
  "domains": [
    {
      "workspace_id": "adapt-debug",
      "domain_id": "tp",
      "revision": 3,
      "schema": [ { "key": "ic_vendor", "label": "IC 厂商", "type": "select", "options": ["Goodix"], "required": true } ],
      "form_data": { "ic_vendor": "Goodix" },
      "stale_fields": ["old_tran_root"],
      "incomplete_required": []
    }
  ]
}
```

> 附 `schema` 是为了让用户端能正确渲染/填充**自定义字段**（否则表单不认识 `x_*`）。
> **同步通道禁止任何写操作**（V1 只拉不推），从物理上杜绝个人本机直改权威库。

---

## 4. 安全与权限管控（重点）

| 面向 | 措施 | 落点 |
|------|------|------|
| **越权写** | 写/导入/恢复=`requireReviewer`；删除=`requireAdmin`；同步通道只读 | 各路由中间件 |
| **目录穿越** | `SAFE_ID` 白名单校验所有路径片段；只 `join(adaptPrereqsDir(), 校验后片段)` | `adapt-prereqs.ts` service |
| **并发覆盖** | `revision` 乐观锁；冲突 409 回传当前版由 UI 决策 | PUT/commit/restore |
| **脏数据写入** | 写入按**生效 schema 校验**：类型、必填（非 draft）、select 值须在 options（未开 `allow_custom_option` 时）；违规返回 **422 + 字段清单** | PUT/import commit |
| **半写损坏** | `safeFileStore` 临时文件+rename+单文件锁 | 所有写 |
| **审计留痕** | 每次写调 `writeAuditLog({action:'adapt_prereq_*', actor:getActor(ctx), target_type:'adapt_prereq', target_id:'{code}/{cid}/{ws}/{domain}'})` | 写路由 |
| **actor 归属** | Web=登录用户名；同步=`x-tahp-actor`；统一 `getActor(ctx)` | 复用现有 |
| **敏感信息** | 前置值含内网盘符/路径，属内网数据；日志**不打印完整 form_data**，仅记 `changed_keys[]`；导出权限=编辑权限 | service/log |
| **上传防炸** | Excel 走 **base64-in-JSON**（无 multipart 依赖）；import 校验解码后 ≤5MB、sheet 数/单元格数上限；用 `exceljs` 安全解析（禁公式执行） | `adapt-prereqs-xlsx.ts` |
| **未知字段** | 导入未知 `field_key` → 仅告警不写入；以中心 field 字典为准 | xlsx import |
| **管理员兜底** | 复用 `deleteReviewer` 式「不能删最后一个 admin」思路；删项目前二次确认 | UI + admin 路由 |

**权限矩阵（最终）**：

| 操作 | 匿名(内网) | reviewer | admin | sync token |
|------|-----------|----------|-------|------------|
| 读列表/详情/历史/导出 | ✅(可选收紧) | ✅ | ✅ | resolve 只读 ✅ |
| 新建/编辑/导入/恢复/建战役 | ❌ | ✅ | ✅ | ❌ |
| 删除项目/战役 | ❌ | ❌ | ✅ | ❌ |

---

## 5. Web 交互设计（友好优先）

### 5.1 页面骨架 `AdaptPrereqsView.vue`

```text
┌ 适配前置 ────────────────────────────────────────────────┐
│ [搜索项目▼]  [+ 新建项目]                                   │
├────────────┬──────────────────────────────────────────────┤
│ 项目列表     │ 项目：X6878-CN                                 │
│ · X6878-CN  │ 战役: [a16→a17] [a17→a18*active] [+ 从历史复制] │
│ · X6890     │ ┌ 域侧栏 ─┬ 表单编辑区 ───────────────────────┐│
│ · …         │ │ TP      │ debug_project [____]              ││
│             │ │ 充电*   │ ic_vendor    [Goodix ▼]           ││
│             │ │ Modem   │ aosp_root ⚠需更新 [____]          ││
│             │ │ …       │ …                                  ││
│             │ └─────────┴────[保存] [导入xlsx] [导出xlsx] [历史]┘│
└────────────┴──────────────────────────────────────────────┘
```

**友好细节**：
- 域侧栏用 Console 同套域定义渲染（TP/充电/Modem…），带「已填/未填」小圆点。
- `version_sensitive` 且 `stale` 的字段：黄底 + ⚠「需为本版本更新」，鼠标悬停解释。
- 保存成功 toast；冲突（409）弹「他人已更新到 rN，[查看差异]/[覆盖]/[放弃]」。
- 未填必填项允许「暂存草稿」，顶部提示「N 个必填未完成」。

### 5.2 升版复用向导（「从历史复制」）

1. 选 `from_os/to_os`（如 17/18）→ 2. 选「基于」旧战役 → 3. 克隆模式默认 **reuse_only** →
4. 生成新战役：`reusable`(IC/马达等)带出，`version_sensitive`(路径)清空并 `stale=true` → 5. 进入编辑逐项补路径。

### 5.3 历史抽屉

revision 列表（时间/操作者/来源/改动字段数）→ 点开看某版快照 → 「恢复为当前」（写新版，不销毁历史）。

---

## 6. Excel 契约

与现有 `AI适配调试_前置信息收集模板.xlsx` 同构（见 `README.md`）：

- Sheet 名 `AD_<domain>` → `workspace=adapt-debug`；第 8 行 `field_key` = `form_data` 键。
- 导出文件名：`prereq_{project_code}_{campaign_id}_{yyyyMMdd}.xlsx`。
- 传输：导入 = `POST {file_b64}`（base64-in-JSON，非 multipart）；导出 = `Buffer` 下载。
- 导入：空单元格默认**不覆盖**（可选 `clear_empty`）；未知列告警；`project_code` 须与 URL 一致；先 `import` 预览 diff → `commit` 落盘（新 revision，`source=excel`）。
- **列表/表格型前置**（如模板 `02_ECC条目` 多行）：落为 `form_data.<key>` = `array<object>`（对应字段 `type=table`）；导入时多行 → 数组，导出时数组 → 多行。

---

## 7. 字段拓展性规划（自定义前置项）

> **诉求**：不同项目 / 不同大版本可能有不同前置要求；Web 收集时要能自定义。
> **原则**：结构与值分离；用**分层 schema** 承载差异，绝不硬编码字段表。

### 7.1 分层 Schema 模型（合并优先级：低 → 高）

```text
base（系统基线，从 Console adapt-debug-domains 同步，只读）
  ⊕ custom-global   （按 workspace×domain，全局生效，admin 维护）
    ⊕ project.custom（本项目所有战役生效，reviewer）
      ⊕ campaign.custom（仅本大版本/战役生效，reviewer）  ← 最高优先级
= 生效 schema（effective schema）
```

- **后者覆盖前者**（标量属性）；`options_add` 类做**累加**去重。
- 生效 schema 是**唯一事实源**：Web 表单渲染、Excel 列、Console 载入全部基于它。
- 由 `GET /…/domains/:ws/:domain/schema?...` 统一产出。

### 7.2 字段定义（FieldDef）

```json
{
  "key": "x_special_cal",
  "label": "特殊标定参数",
  "type": "select",              // text|textarea|number|bool|date|select|multiselect|table
  "required": false,
  "options": ["A", "B"],
  "allow_custom_option": true,   // 允许填写时现场新增选项
  "category": "version_sensitive",
  "scope": "campaign",           // global|project|campaign（system 字段为 base）
  "source": "custom",            // system|custom
  "order": 120,
  "deprecated": false,
  "created_by": "zhangsan",
  "created_at": "2026-07-16T..."
}
```

### 7.3 两类扩展操作

| 操作 | 语义 | 载体 |
|------|------|------|
| **新增自定义字段** | 加一个基线没有的字段（`x_` 前缀） | `schema.custom.json.additions[ws][domain][]` |
| **覆盖基线字段** | 就地调整已有字段属性（**不改 key/type**） | `schema.custom.json.overrides[ws][domain][key]` |

覆盖白名单属性（仅这些可被 override，安全起见）：

```json
"overrides": {
  "aosp_root":       { "required": true },       // 某项目强制必填
  "old_tp_firmware": { "hidden": true },         // 本大版本不需要 → 隐藏
  "ic_vendor":       { "options_add": ["Novatek"] },
  "debug_project":   { "order": 5, "label": "调试项目(内部代号)" }
}
```

> **不允许** override `type` / `key`；**不允许**新增字段与系统 key 同名（防结构漂移）。

### 7.4 自定义下拉选项（填写时现场加）

- `type=select/multiselect` 且 `allow_custom_option=true` 的字段，填写区出现「+ 自定义…」。
- 新选项经 `POST /…/fields/:key/options` **回写字段字典**（去重、审计），后续所有人可选。
- 若字段不允许现填新增，仍可由管理该 scope 的人在「字段管理」里加选项。

### 7.5 Web 交互（字段管理，友好优先）

编辑区顶部「**+ 自定义字段**」向导：

1. **作用域**：`本战役`（默认）/ `本项目` / `全局本域`（后者需 admin）
2. **类型** → 3. **显示名 label** → 4. **key**（系统自动补 `x_` 前缀，校验唯一）
3. **选项**（select 时；可勾「允许填写时新增选项」）
4. **升版策略/分类**：按命名规则预判（含 `path/root/old/new` → `version_sensitive`；否则 `reusable`），可改。

每个字段行右侧「⋯」菜单：`本作用域覆盖`（设必填/隐藏/加选项/调序）、`弃用`、`改选项`。
基线字段**可覆盖、可弃用（隐藏）、不可物理删除**——已填历史值永远可见（灰显）。

### 7.6 Excel 随 schema 动态列

- 导出：列 = 该战役**生效 schema**；自定义字段列头加 `[自定义]` 标注。
- `99_字段字典` sheet 输出**完整生效字典**（key/label/type/options/scope/category）。
- 导入：以中心生效 schema 校验；未知列 → 告警，并提供选项「登记为**战役级**自定义字段后导入」（一步补结构+值）。

### 7.7 大版本复用中的自定义字段

- 自定义字段同样带 `category`：克隆 `reuse_only` 时——`reusable` 自定义字段**结构+值继承**；`version_sensitive` **结构继承、值清空并 stale**。
- `campaign` 级自定义字段：克隆新战役时**结构默认带过去**（否则新版本会丢字段），值按 category 处理。

### 7.8 安全与治理

| 面向 | 措施 |
|------|------|
| 命名冲突 | 自定义 key 强制 `^x_[a-z0-9_]{1,48}$`；禁与系统 key 同名 |
| 权限分级 | global 作用域 = **admin**（影响所有项目）；project/campaign = reviewer |
| 结构漂移 | override 仅白名单属性；不可改 type/key；base 只读 |
| 悬空值 | 字段只 `deprecated` 不物删；已填值保留可见 |
| 留痕 | 所有 schema 变更写 audit-log：`adapt_prereq_schema_updated`（记 scope/key/change） |
| 误伤 | 弃用/删自定义字段前二次确认；提示「N 处已填该字段」 |

---

## 8. 分步落地（每步 ≤8 文件 + 验收）

> 每步开工前，先按用户三步工作流给出**该步文件级 diff 提案**，确认后再写码。

| PR | 名称 | 仓 | 文件 | 验收命令/口径 |
|----|------|-----|------|----------------|
| **A1** | 存储+CRUD+resolve | bff | `paths.ts`·`services/adapt-prereqs.ts`·`services/adapt-prereqs-fields.ts`·`audit-log.ts`·`routes/adapt-prereqs.ts`·`routes/sync.ts`·`index.ts`（7） | `curl` 建项目→建战役→PUT 域→`sync/resolve` 能取回；乐观锁 409 可复现 |
| **A1.5** | 分层 schema + 生效解析 | bff | `services/adapt-prereqs-fields.ts`（扩展）·`services/adapt-prereqs-schema.ts`（新增）·`routes/adapt-prereqs.ts`（+schema 接口）（3） | `GET …/schema` 返回 base；加战役级自定义字段后合并出现；global=admin 校验 |
| **A2** | 后台编辑页 + 字段管理 | bff/client | `AdaptPrereqsView.vue`·`main.ts`·`App.vue`·`api.ts`（4） | 登录可增删改存；「+自定义字段」按 scope 生效；非 admin 无删除/无 global 自定义 |
| **A3** | 历史+恢复 | bff(+client) | `services/adapt-prereqs.ts`·`routes/adapt-prereqs.ts`·`AdaptPrereqsView.vue`（3） | 改 3 次→看到 3 版→恢复 r1 生成 r4 |
| **A4** | Excel 导入导出（随 schema 动态列） | bff(+client) | `services/adapt-prereqs-xlsx.ts`·`routes/adapt-prereqs.ts`·`AdaptPrereqsView.vue`·`api.ts`（4） | 含自定义字段导出→改→导入预览 diff→commit，往返不丢 key；未知列可「登记为自定义后导入」 |
| **A5** | 克隆升版（含自定义字段继承） | bff(+client) | `services/adapt-prereqs.ts`·`services/adapt-prereqs-schema.ts`·`AdaptPrereqsView.vue`（3） | `reuse_only` 克隆后路径空+stale、IC 在；自定义字段按 category 继承结构/值 |
| **A6** | 用户端载入（选项目→拉全部前置→自动填表） | tahp-console | `central-client.ts`·适配调试路由·adapt-debug 页（≤4，开工前 grep 定位） | 选/输项目→一次拉回该战役全部域→自动填充前置表单；默认仅填空；stale 黄标；自定义字段可显示。**不含**启动适配 |

> A1 后即可用 curl 打通「拉取」闭环；A1.5 起结构可扩展；A2 起提供中心编辑 GUI；A6 打通用户端「选项目→自动填表」。

---

## 9. 待你拍板的实现级决策

| # | 决策点 | 建议默认 |
|---|--------|----------|
| 1 | 读接口是否也加 `requireReviewer` | **不加**（与现有 knowledge 读一致，靠前端守卫）；如要更严可加 |
| 2 | 是否新增 `editor` 角色 | **不新增**，复用 `reviewer` 即可写（现网仅 admin/reviewer） |
| 3 | Excel 解析库 | 优先复用仓内已有依赖；无则新增 `exceljs`（比 `xlsx` 更安全，禁公式） |
| 4 | 域字段字典来源 | 从 Console `adapt-debug-domains.ts` **人工同步**一份为 `schema/base.json`（避免跨仓 import）；后续可脚本化 |
| 5 | 历史保留上限 | 每域最近 **50** 版快照，更早仅留 `log.jsonl` |
| 6 | 自定义 key 前缀强制 `x_` | **是**（`^x_[a-z0-9_]{1,48}$`，防与系统字段冲突） |
| 7 | 自定义作用域→角色 | global=**admin**；project/campaign=**reviewer** |
| 8 | 是否支持「自定义业务域」（新维度，非仅字段） | **V1 不做**；V1 只做自定义字段/选项/覆盖，V2 再评估自定义域 |

---

## 10. 验证与自检（遵守 `tahp-verify-commit`）

每个改 bff 代码的 PR：

```bash
cd easyadapter_bff
npm run build            # TS 编译通过
npx tsx scripts/smoke-test.ts   # 若补充前置库 smoke 用例
```

改 tahp-console（A6）：

```bash
cd tahp-console
npm test                 # 相关用例
npm run build
```

**自检清单**：diff 仅含任务文件；未提交 `.env`/凭据；`adapt-prereqs/` 数据不入 Git；敏感链（paths/sync）改动写明重启与验证步骤。

---

## 11. 一句话开工口令

确认 §9 后，我按 **A1** 出「文件级 diff 提案」（仍先清单、再落码），逐 PR 推进到 A6。
