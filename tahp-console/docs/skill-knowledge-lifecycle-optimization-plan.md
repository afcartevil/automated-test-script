# Skill & 知识库生命周期管控优化计划

> 版本：v1.0 | 创建日期：2025-05-28 | 状态：待实施

---

## 1. 问题分析

### 1.1 现状

| 对象 | 现有能力 | 缺失能力 |
|------|---------|---------|
| **Skill 草稿** | 创建 / 审核(approve→激活) / 拒绝 | 删除草稿、废弃、归档、批量清理 |
| **已激活 Skill** | 从磁盘读取 / 展示列表 | 废弃(deprecate)、下线(deactivate)、删除磁盘文件 |
| **知识条目** | 创建 / 编辑 / 归档(软删除) | 物理删除、批量归档、过期管理 |
| **知识文档** | 上传 / 解析 / 物理删除 | 批量清理、过期提醒 |

### 1.2 代码层面的具体缺失

```
现状审计结果：
─────────────────────────────────────────────────────────────
1. SkillDraft.status 只有 'draft' | 'reviewing' | 'approved' | 'rejected'
   → 缺少 'deprecated' 和 'archived' 状态

2. 无 DELETE /api/tahp/knowledge/skill-drafts/:draftId 路由
   → 草稿无法删除，rejected 草稿永久堆积

3. getActivatedSkills() 读取 skills/.claude/skills/ 下所有目录
   → 不过滤 frontmatter 中的 status 字段，无法跳过已废弃 Skill

4. scanTahpSkills() 同样不检查 status
   → 技能库页面无法区分活跃/废弃 Skill

5. SkillsView.vue 中 `archived` 变量已预留但服务端始终返回 []
   → 归档列表形同虚设

6. 知识条目 deleteKnowledgeEntry() 实际执行软删除(status → 'archived')
   → 无物理删除入口，归档条目永久堆积

7. 无审计日志机制
   → 无法追溯谁在何时删除/废弃了什么
```

---

## 2. 设计目标

1. **Skill 草稿全生命周期**：draft → approved → deprecated → archived，每个状态均可达可退
2. **已激活 Skill 下线能力**：支持废弃（保留文件但标记）和下线（移除磁盘文件）
3. **知识条目清理能力**：支持物理删除和批量归档清理
4. **批量操作**：对低风险对象（rejected 草稿、长期未用 Skill）支持批量清理
5. **安全策略**：废弃优先于删除、关键操作二次确认、全量审计日志
6. **前端可观测性**：统计面板展示各状态数量、废弃/归档筛选器

---

## 3. 状态机设计

### 3.1 Skill 草稿状态流转

```
                    ┌──────────┐
                    │  created │
                    └────┬─────┘
                         │
                    ┌────▼─────┐
              ┌────►│  draft   │◄────────────────────┐
              │     └────┬─────┘                     │
              │          │ submit                    │ restore
              │     ┌────▼──────┐                    │
              │     │ reviewing │                    │
              │     └──┬────┬───┘                    │
              │        │    │                        │
              │ approve│    │reject                  │
              │   ┌────▼──┐ ┌▼────────┐              │
              │   │approved│ │rejected │──── archive─►│
              │   └──┬──┬──┘ └─────────┘              │
              │      │  │                             │
              │      │  │ deprecate                   │
              │      │  └──────────┐                  │
              │      │        ┌────▼──────┐           │
              │      │        │ deprecated│── archive─┤
              │      │        └───────────┘           │
              │      │                                │
              │      │ deactivate(下线磁盘文件)        │
              │      │                                │
              │      │   ┌──────────┐                 │
              └──────┴───│ archived │─────────────────┘
                         └──────────┘
```

### 3.2 状态含义

| 状态 | 含义 | 磁盘文件 | 列表可见 | 统计计入 |
|------|------|----------|---------|---------|
| `draft` | 草稿，可编辑 | 无 | ✓（工坊） | ✓ |
| `reviewing` | 审核中 | 无 | ✓（工坊） | ✓ |
| `approved` | 已批准并激活 | 有（active） | ✓（技能库+工坊） | ✓ |
| `rejected` | 已拒绝 | 无 | ✓（工坊，灰色） | ✓ |
| `deprecated` | 已废弃（过时/不推荐） | 有（status: deprecated） | ✓（技能库，标记废弃） | ✓ |
| `archived` | 已归档 | 无（移到 .archive） | 仅筛选器开启时 | ✗ |

---

## 4. 后端实施计划

### 4.1 Phase 1：数据模型扩展

**涉及文件**：`packages/server/src/routes/tahp/knowledge.ts`

**改动项**：

| 编号 | 改动 | 说明 |
|------|------|------|
| M1 | `SkillDraft.status` 联合类型扩展 | 增加 `'deprecated' \| 'archived'` |
| M2 | `SkillDraft` 新增字段 | `deprecated_at?: string`、`deprecated_by?: string`、`deprecate_reason?: string`、`archived_at?: string`、`archived_by?: string` |
| M3 | `getActivatedSkills()` 增加 status 过滤 | 读取 frontmatter `status` 字段，跳过 `status: deprecated` 和已删除目录 |
| M4 | `listSkillDrafts()` 支持多状态筛选 | 参数 `status` 支持逗号分隔多值，默认排除 `archived` |
| M5 | `KnowledgeEntry.status` 新增 `'deleted'` | 区分软归档和物理删除标记 |

### 4.2 Phase 2：Skill 草稿管理路由

**新增路由**：

| 方法 | 路径 | 功能 |
|------|------|------|
| `DELETE` | `/api/tahp/knowledge/skill-drafts/:draftId` | 删除草稿（仅 draft/rejected 状态） |
| `POST` | `/api/tahp/knowledge/skill-drafts/:draftId/deprecate` | 废弃已激活的 Skill（修改 frontmatter status，保留文件） |
| `POST` | `/api/tahp/knowledge/skill-drafts/:draftId/deactivate` | 下线已激活的 Skill（删除磁盘文件，草稿标记 archived） |
| `POST` | `/api/tahp/knowledge/skill-drafts/:draftId/archive` | 归档草稿（任意状态 → archived） |
| `POST` | `/api/tahp/knowledge/skill-drafts/:draftId/restore` | 恢复归档草稿（archived → 原始状态） |
| `POST` | `/api/tahp/knowledge/skill-drafts/bulk-cleanup` | 批量清理 rejected 草稿 |
| `POST` | `/api/tahp/knowledge/skill-drafts/bulk-deprecate` | 批量废弃已激活 Skill |

**路由实现要点**：

```typescript
// DELETE — 仅允许 draft/rejected 状态
// 1. 读取草稿 JSON 文件
// 2. 检查状态 → 非 draft/rejected 返回 409
// 3. 删除 JSON 文件
// 4. 写入审计日志

// POST deprecate — 废弃已激活 Skill
// 1. 读取草稿，验证 status === 'approved'
// 2. 读取磁盘 SKILL.md，将 frontmatter status 改为 'deprecated'
// 3. 写回 SKILL.md
// 4. 更新草稿 JSON：status → 'deprecated'，记录 deprecated_at/by/reason
// 5. 写入审计日志

// POST deactivate — 下线（物理移除）
// 1. 读取草稿，验证 status ∈ {approved, deprecated}
// 2. 将 skills/.claude/skills/{skillId}/ 整个目录移到 skills/.claude/.archive/{skillId}/
// 3. 更新草稿 JSON：status → 'archived'，记录 archived_at/by
// 4. 清除 scanTahpSkills 缓存
// 5. 写入审计日志

// POST bulk-cleanup — 批量清理
// 1. 读取所有草稿，筛选 status === 'rejected'
// 2. 批量删除 JSON 文件
// 3. 返回清理数量
// 4. 写入审计日志（批量记录）
```

### 4.3 Phase 3：知识条目管理增强

**新增/修改路由**：

| 方法 | 路径 | 功能 |
|------|------|------|
| `DELETE` | `/api/tahp/knowledge/entries/:entryId/hard` | 物理删除条目（从 JSON 文件 + 向量索引中移除） |
| `POST` | `/api/tahp/knowledge/entries/bulk-archive` | 批量归档（按条件筛选） |
| `POST` | `/api/tahp/knowledge/entries/bulk-delete` | 批量物理删除已归档条目 |
| `GET` | `/api/tahp/knowledge/stats/enhanced` | 增强统计（含各状态分布、过期条目数、废弃 Skill 数） |

### 4.4 Phase 4：审计日志

**新增文件**：`packages/server/src/services/tahp/audit-log.ts`

**审计事件类型**：

```typescript
type AuditAction =
  | 'skill_draft_deleted'
  | 'skill_draft_deprecated'
  | 'skill_draft_deactivated'
  | 'skill_draft_archived'
  | 'skill_draft_restored'
  | 'skill_bulk_cleanup'
  | 'skill_bulk_deprecate'
  | 'entry_hard_deleted'
  | 'entry_bulk_archived'
  | 'entry_bulk_deleted'

interface AuditLogEntry {
  id: string           // al-{timestamp}-{random}
  timestamp: string    // ISO 8601
  action: AuditAction
  actor: string        // 'admin' | 用户名
  target_type: 'skill_draft' | 'knowledge_entry' | 'document'
  target_id: string
  target_name?: string
  details?: Record<string, unknown>  // 操作前快照关键字段
  reason?: string
}
```

**存储方式**：JSONL 追加写入 `knowledge-base/.kb-data/audit-log.jsonl`，按天自动轮转。

---

## 5. 前端实施计划

### 5.1 Phase 1：Skill 工坊增强

**涉及文件**：`packages/client/src/views/tahp/KnowledgeBaseView.vue`

**改动项**：

| 编号 | 改动 | 说明 |
|------|------|------|
| F1 | 草稿列表状态筛选器扩展 | 增加 "已废弃"、"已归档" 选项，默认排除 archived |
| F2 | 草稿操作列扩展 | draft/rejected 行增加"删除"按钮；approved 行增加"废弃"按钮 |
| F3 | 批量清理按钮 | 列表上方增加"清理已拒绝草稿"按钮（显示待清理数量） |
| F4 | 删除确认弹窗 | 二次确认，显示草稿名称、来源条目数、创建时间 |
| F5 | 废弃确认弹窗 | 要求填写废弃原因（必填），二次确认 |
| F6 | 归档恢复操作 | archived 状态的行显示"恢复"按钮 |

### 5.2 Phase 2：技能库增强

**涉及文件**：`packages/client/src/views/hermes/SkillsView.vue`

**改动项**：

| 编号 | 改动 | 说明 |
|------|------|------|
| F7 | 技能卡片状态标识 | deprecated 状态显示橙色"已废弃"角标 |
| F8 | 技能详情操作栏 | 增加"废弃"和"下线"按钮 |
| F9 | 批量废弃模式 | 多选 + 批量操作栏 |
| F10 | 归档分类展示 | 利用已有 `.archive` 分类，展示已下线的 Skill |

### 5.3 Phase 3：知识库管理增强

**涉及文件**：`packages/client/src/views/tahp/KnowledgeBaseView.vue`

**改动项**：

| 编号 | 改动 | 说明 |
|------|------|------|
| F11 | 条目列表增加"已归档"筛选开关 | toggle 显示/隐藏 archived 条目 |
| F12 | 归档条目行增加"物理删除"按钮 | 红色危险操作，二次确认 |
| F13 | 批量归档/清理工具栏 | 按模块/创建时间筛选 + 批量操作 |
| F14 | 统计面板增强 | 展示各状态分布饼图、废弃 Skill 数、过期条目数 |

### 5.4 Phase 4：前端 API 层

**涉及文件**：`packages/client/src/api/tahp/knowledge.ts`

**新增 API 函数**：

```typescript
// Skill 草稿管理
export function deleteSkillDraft(draftId: string): Promise<{ deleted: string }>
export function deprecateSkillDraft(draftId: string, reason: string): Promise<SkillDraft>
export function deactivateSkill(draftId: string): Promise<SkillDraft>
export function archiveSkillDraft(draftId: string): Promise<SkillDraft>
export function restoreSkillDraft(draftId: string): Promise<SkillDraft>
export function bulkCleanupDrafts(): Promise<{ cleaned: number }>
export function bulkDeprecateSkills(draftIds: string[], reason: string): Promise<{ deprecated: number }>

// 知识条目管理
export function hardDeleteEntry(entryId: string): Promise<{ deleted: string }>
export function bulkArchiveEntries(filter: { module?: string; before?: string }): Promise<{ archived: number }>
export function bulkDeleteArchived(filter?: { module?: string }): Promise<{ deleted: number }>

// 增强统计
export function getEnhancedStats(): Promise<EnhancedStats>
```

---

## 6. 安全策略

### 6.1 操作分级

| 风险等级 | 操作 | 安全要求 |
|----------|------|---------|
| **低** | 删除 draft/rejected 草稿 | 二次确认弹窗 |
| **低** | 归档草稿 | 可直接操作，支持恢复 |
| **中** | 废弃已激活 Skill | 二次确认 + 废弃原因必填 |
| **中** | 物理删除知识条目 | 二次确认 + 显示引用次数 |
| **高** | 下线已激活 Skill（移除磁盘文件） | 二次确认 + 原因 + 显示使用次数 |
| **高** | 批量操作 | 二次确认 + 显示影响范围 + 仅允许低风险对象 |

### 6.2 防误操作机制

1. **废弃优先于删除**：废弃只改 frontmatter status，文件保留，随时可恢复
2. **归档可恢复**：归档操作只是移动文件到 `.archive/`，支持一键恢复
3. **批量操作白名单**：批量清理只允许 `rejected` 状态草稿；批量废弃只允许 `approved` 状态 Skill
4. **引用保护**：下线 Skill 前检查 `total_usage_count`，高引用量给出强警告
5. **审计日志**：所有状态变更操作记录到 JSONL 审计日志，不可逆

### 6.3 恢复机制

| 操作 | 恢复方式 |
|------|---------|
| 删除草稿(draft/rejected) | 不可恢复（JSON 文件已删除） |
| 归档草稿 | `restore` → 恢复为归档前状态 |
| 废弃 Skill | `approve` → 重新激活（改回 frontmatter status: active） |
| 下线 Skill | 从 `.archive/` 目录移回原位 → 重新激活 |
| 物理删除条目 | 不可恢复 |

---

## 7. 实施优先级

| 优先级 | Phase | 内容 | 预估工作量 |
|--------|-------|------|-----------|
| **P0** | Phase 1 + Phase 2 | 数据模型 + 草稿删除/废弃/归档路由 | 1.5 天 |
| **P1** | Phase 3 | 知识条目增强（物理删除、批量归档） | 1 天 |
| **P1** | Phase 4 | 审计日志基础设施 | 0.5 天 |
| **P2** | 前端 Phase 1 | Skill 工坊草稿管理 UI | 1 天 |
| **P2** | 前端 Phase 2 | 技能库废弃/下线 UI | 1 天 |
| **P3** | 前端 Phase 3 | 知识库管理增强 UI | 0.5 天 |
| **P3** | 前端 Phase 4 | API 层 + 统计面板增强 | 0.5 天 |

**总计预估**：6 个工作日

---

## 8. 验收标准

### 8.1 功能验收

- [ ] Skill 草稿列表可按状态筛选（含 deprecated / archived）
- [ ] 可删除 draft/rejected 状态草稿
- [ ] 可废弃已激活的 Skill（frontmatter status 变为 deprecated，文件保留）
- [ ] 可下线已激活的 Skill（磁盘文件移到 .archive）
- [ ] 可批量清理所有 rejected 草稿
- [ ] 可批量废弃多个已激活 Skill
- [ ] 可物理删除知识条目（JSON + 向量索引双清）
- [ ] 可批量归档/删除过期知识条目
- [ ] 所有操作记录到审计日志
- [ ] 废弃的 Skill 在 AI Agent 扫描时被自动跳过

### 8.2 安全验收

- [ ] 删除/废弃/下线操作均有二次确认
- [ ] 废弃操作要求填写原因
- [ ] 批量操作仅允许低风险对象
- [ ] 审计日志不可逆追加写入
- [ ] TypeScript 编译零错误
- [ ] Vite 生产构建零错误

---

## 9. 附录：涉及文件清单

| 文件路径 | 改动类型 | 说明 |
|---------|---------|------|
| `packages/server/src/routes/tahp/knowledge.ts` | 修改 | 数据模型扩展 + 7 个新路由 |
| `packages/server/src/services/tahp/audit-log.ts` | 新建 | 审计日志服务 |
| `packages/server/src/controllers/hermes/skills.ts` | 修改 | scanTahpSkills 增加 deprecated 过滤 |
| `packages/client/src/api/tahp/knowledge.ts` | 修改 | 新增 ~12 个 API 函数 + 类型 |
| `packages/client/src/views/tahp/KnowledgeBaseView.vue` | 修改 | 草稿管理 UI + 知识库管理增强 |
| `packages/client/src/views/hermes/SkillsView.vue` | 修改 | 废弃/下线操作 UI |
