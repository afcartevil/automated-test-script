# 适配前置信息库 — 中心权威方案设计

> **状态**：设计提案（待确认后开工）  
> **目标**：业务可在线编辑；本机 EasyAdapter 用现有中心连接拉取；支持 Excel 导入导出；历史可追溯；大版本升级（16→17→18）可复用。  
> **非目标**：飞书 CLI / 每人文档 ACL；自研完整电子表格引擎。

---

## 1. 问题与原则

| 诉求 | 设计原则 |
|------|----------|
| 多人在线改 | 中心 Web 编辑，审核员/编辑角色登录即可 |
| 每人本机可取 | 复用 `TAHP_CENTRAL_URL` + `TAHP_CENTRAL_TOKEN` |
| Excel 互通 | 与现有 `AI适配调试_前置信息收集模板.xlsx` 同构导入导出 |
| 可追溯 | 中心侧 revision + 变更快照（不必强绑 Git） |
| 大版本复用 | **项目档案**跨 Android 大版本挂载；路径类字段**分版本覆盖**，器件/业务常量**继承复用** |

---

## 2. 核心概念

```text
ProjectProfile（项目档案，长期存在）
  project_code          # 业务主键，如 X6878-CN
  product_line / name
  └── AdaptCampaign（适配战役 / 大版本跃迁）
        campaign_id       # 如 a16-to-a17、a17-to-a18
        from_os / to_os   # 16 / 17 / 18（语义化，非强制枚举）
        status            # draft | active | archived
        based_on_campaign_id?  # 从哪次战役复制而来
        └── DomainBundle（工作区 × 业务域 一份前置值）
              workspace_id + domain_id
              form_data{}          # 与 Console field_key 对齐
              revision             # 单调递增
              updated_at / by
```

### 2.1 为何拆 Project × Campaign

- **16→17** 与 **17→18** 往往是两次适配，路径/基线不同，但 IC 型号、马达类型等大量相同。  
- 新建 `a17-to-a18` 时：`clone from a16-to-a17` → 清空/高亮「路径类」字段 → 保留「常量类」。  
- 历史按 **campaign** 归档，不互相覆盖。

### 2.2 字段分类（复用策略）

| 分类 | 示例 | 升版默认策略 |
|------|------|----------------|
| `reusable` | ic_vendor / ic_model / motor_type / fp_vendor / bom_name | **继承**上一战役 |
| `version_sensitive` | *_path* / aosp_root / old_tran_root / PROJ_FILE_* / vnd_path_* | **不继承**或标「待更新」 |
| `campaign_meta` | mode / pillar_required / upgrade_scenario | 继承但允许改 |
| `notes` | user_notes | 清空或不继承 |

中心维护一张 **field_key → category** 小表（可先按命名规则自动：含 `path`/`root`/`_old`/`_new` → version_sensitive）。

---

## 3. 存储布局（BFF `data/`）

```text
data/.tahp/adapt-prereqs/
  index.json                          # 项目列表摘要
  projects/
    {project_code}/
      profile.json                    # 档案
      campaigns/
        {campaign_id}/
          meta.json                   # from_os/to_os/based_on/...
          domains/
            {workspace_id}__{domain_id}.json   # 当前权威值
          history/
            {workspace_id}__{domain_id}/
              r{revision}.json        # 每次写入整包快照
              log.jsonl               # 追加：谁/何时/摘要/来源(ui|excel|api|clone)
```

单文件域包示例 `adapt-debug__tp.json`：

```json
{
  "schema_version": 1,
  "project_code": "X6878-CN",
  "campaign_id": "a16-to-a17",
  "workspace_id": "adapt-debug",
  "domain_id": "tp",
  "revision": 12,
  "form_data": { "debug_project": "...", "ic_vendor": "Goodix" },
  "field_meta": {
    "old_tp_firmware": { "category": "version_sensitive", "stale": true }
  },
  "updated_at": "2026-07-15T12:00:00Z",
  "updated_by": "zhangsan",
  "source": "ui"
}
```

> `history/` **默认可入 Git（与 skill 类似可配置）**；日常读写用本地文件即可。联调阶段可不推远程。

待审包式大体积二进制不进本库（路径字符串即可）。

---

## 4. API 设计

前缀约定：

| 调用方 | 鉴权 | 前缀 |
|--------|------|------|
| 中心 Web（审核员） | 登录 Bearer（现有 reviewers） | `/api/tahp/adapt-prereqs/...` |
| 本机 Console | `TAHP_CENTRAL_TOKEN`（现有 sync 鉴权） | `/api/tahp/sync/adapt-prereqs/...` |

### 4.1 档案与战役

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/projects` | 列表（code/name/活跃战役） |
| POST | `/projects` | 新建档案 |
| GET | `/projects/:code` | 详情 + campaigns[] |
| POST | `/projects/:code/campaigns` | 新建战役；body 可带 `based_on_campaign_id` + `clone_mode` |
| PATCH | `/projects/:code/campaigns/:cid` | 改状态 / 备注 |

`clone_mode`：

- `full`：全字段复制  
- `reuse_only`：**默认推荐** — 仅 `reusable` + `campaign_meta`，路径类留空并 `stale=true`  
- `empty`：只建空战役  

### 4.2 域数据（Web + Sync 共用语义）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `.../campaigns/:cid/domains` | 该战役下已填域列表 |
| GET | `.../campaigns/:cid/domains/:ws/:domain` | 当前权威 `form_data` |
| PUT | 同上 | 整表覆盖；`revision` 乐观锁（If-Match / body.revision） |
| PATCH | 同上 | 部分 field 更新 |

### 4.3 历史

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `.../domains/:ws/:domain/history?limit=` | revision 列表（时间、操作者、source、摘要） |
| GET | `.../domains/:ws/:domain/history/:rev` | 某版完整快照 |
| POST | `.../domains/:ws/:domain/restore` | body:`{ revision }` → 写为新 revision（不删历史） |

### 4.4 Excel

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `.../campaigns/:cid/export.xlsx` | 导出与模板同构的 xlsx（可带该战役数据） |
| POST | `.../campaigns/:cid/import` | JSON `{file_b64}`（base64，无 multipart）；返回 diff 预览 |
| POST | `.../campaigns/:cid/import/commit` | 确认写入（生成新 revision） |

导入规则：

1. 解析 Sheet 名 `AD_tp` → `workspace=adapt-debug, domain=tp`  
2. `project_code` 必须与 URL 中档案一致（或导入时绑定）  
3. 空单元格 = **不覆盖**（保留原值）；可选 `clear_empty=1` 强制清空  
4. 未知 `field_key` → 警告列表，默认识别不导入  
5. 必填缺失 → 允许暂存 `draft`，Console 拉取时标 `incomplete_fields[]`

### 4.5 本机拉取（Sync）

```http
GET /api/tahp/sync/adapt-prereqs/resolve
  ?project_code=X6878-CN
  &campaign_id=a17-to-a18          # 可选；默认该项目 active campaign
  &workspace_id=adapt-debug
  &domain_id=charging
```

响应：

```json
{
  "project_code": "X6878-CN",
  "campaign_id": "a17-to-a18",
  "from_os": "17",
  "to_os": "18",
  "workspace_id": "adapt-debug",
  "domain_id": "charging",
  "revision": 3,
  "form_data": { "...": "..." },
  "stale_fields": ["aosp_root", "old_tran_root"],
  "incomplete_required": [],
  "updated_at": "...",
  "updated_by": "..."
}
```

Console：适配调试页增加「从中心载入」→ 选 project + campaign（可默认 active）→ 写入表单；`stale_fields` 黄标提醒人工核对路径。

---

## 5. 中心 Web UX

新菜单：**适配前置**（所有审核员可读写；admin 可删战役）

### 5.1 页面结构

```text
适配前置
├─ 项目列表（搜索 / 新建）
├─ 项目详情
│    ├─ 战役 Tab：a16→a17 | a17→a18 | +从历史战役复制
│    ├─ 域侧栏：与 Console 域一致（TP/充电/Modem…）
│    ├─ 表单编辑（按 field 字典渲染）+ 保存
│    ├─ 工具条：导入 Excel | 导出 Excel | 历史
│    └─ 历史抽屉：revision 列表 → 查看 diff → 恢复为当前
└─ （可选）字段字典只读页
```

### 5.2 升版复用交互

1. 点「新增大版本战役」  
2. 选择 `from_os / to_os`（如 17 / 18）  
3. 「基于」下拉选 `a16-to-a17`  
4. 克隆模式默认 **reuse_only**  
5. 进入后路径类字段空且标「需为本版本更新」；IC 等已带出  

### 5.3 并发

- PUT 带 `revision`；冲突返回 409 + 服务端当前版，UI 提示合并/覆盖。  
- 不做单元格级 OT（表格量小，整域保存即可）。

---

## 6. Excel 契约（与现模板对齐）

| 模板元素 | 中心语义 |
|----------|----------|
| `01_项目登记.project_code` | ProjectProfile |
| Sheet `AD_*` / `FA_*` / `CC_*` | DomainBundle |
| 第 8 行 field_key | form_data keys |
| 黄底数据行 | 导入数据行（每战役导出通常 **一行** = 该项目该战役） |
| `02_ECC条目` | 写入 `ecc_entries` 或 `form_data.ecc_entries_json` |
| `99_字段字典` | 导出时可附带；导入以中心字典为准校验 |

导出文件名建议：

`prereq_{project_code}_{campaign_id}_{yyyyMMdd}.xlsx`

---

## 7. Console 集成点

| 位置 | 行为 |
|------|------|
| 适配调试 / 特性适配 / 运营商 | 「从中心载入前置」对话框 |
| 选择 | project_code → campaign（默认 active）→ 当前 domain |
| 载入后 | 合并进表单；不自动开跑；stale 字段列表提示 |
| 未配中心 | 隐藏入口或提示配置 CENTRAL_URL（与 Skill 同步一致） |

**不**在未确认下载时静默覆盖用户已填内容：默认「仅填空」；可选「全部覆盖」。

---

## 8. 审计与历史粒度

| 层 | 内容 |
|----|------|
| 域 history 快照 | 每次成功写入一整份 form_data |
| log.jsonl | actor, source(ui/excel/api/clone/restore), revision, field_change_count |
| 中心 audit-log | 关键写操作挂 `adapt_prereq_*` action（与现有审计页可检索） |

保留策略：每域最近 **N=50** 版快照；更早可只留 log（可配置）。

---

## 9. 权限

| 操作 | 角色 |
|------|------|
| 读项目/域/历史/导出 | reviewer + admin；sync token 只读 resolve |
| 写/导入/恢复/新建战役 | reviewer + admin |
| 删除项目/战役 | admin only |

个人研发本机 **不能** 用 central token 改中心库（与 Skill 包「提交≠直写 live」一致）；改数走 Web 或「提交变更单」（V2 可选，V1 不做）。

---

## 10. 分步落地（建议）

| Step | 仓 | 交付 | 验收 |
|------|-----|------|------|
| **A0** | 文档 | 本文定稿；field 分类规则表 | 决策对齐 |
| **A1** | bff | 存储 + CRUD + resolve（sync） | Console curl 能拉到 form_data |
| **A2** | bff client | 项目/战役/域编辑页 | 网页可改可存 |
| **A3** | bff | history + restore | 可看旧版并恢复 |
| **A4** | bff | Excel import/export（对齐现模板） | 往返不丢 key |
| **A5** | bff | clone campaign `reuse_only` | 17→18 路径空、常量在 |
| **A6** | console | 「从中心载入」 | 填表成功 + stale 提示 |
| **A7** | 双仓 | 单测/smoke + 说明 | SELF-CHECK 级自检 |

单批仍遵守「影响文件 ≤8」时可按上表拆 PR。

---

## 11. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 路径泄漏（内网盘符） | 仅内网中心；导出权限同编辑；日志不打印完整 secret |
| Excel 与 UI 字段漂移 | 以 Console 域定义为准生成字典；导入未知列告警 |
| 误用旧战役路径 | stale 标记 + Console 强提示；active campaign 唯一 |
| 历史膨胀 | N 版上限；可选不入 Git |
| 与 layout 云同步混淆 | 文档写清：layout=表单结构；prereq=按项目填的值 |

---

## 12. 待确认项（请拍板）

| # | 项 | 建议默认 |
|---|-----|----------|
| 1 | 历史是否必须进 GitLab | **否**；文件快照即可，审计够用 |
| 2 | 每项目是否允许多个 active campaign | **否**；同时仅 1 个 active |
| 3 | clone 默认模式 | **reuse_only** |
| 4 | V1 是否含「本机回写中心」 | **否**；只拉不推 |
| 5 | OS 版本字段形态 | 自由文本 `from_os`/`to_os`（"16""17""18"），不做死枚举 |
| 6 | 首期覆盖工作区 | **adapt-debug 全部域**；FA/CC 结构预留、页可后开 |

---

## 13. 与飞书关系（再次收口）

- 权威：**仅 BFF**。  
- 飞书若偶发使用：人工导出 Excel → 中心导入；不接飞书 API。  

---

## 14. 确认后开工口令

确认 §12 后，按 **A1 → A6** 增量实现；先出 A1 API 契约单测再上网页。
