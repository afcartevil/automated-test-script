# 知识库导入后自动转 Skill — 完整业务方案

> 版本：v1.0 | 日期：2026-05-28  
> 范围：tahp-console 知识库模块增强

---

## 1. 业务背景与目标

当前知识库系统已完成：
- Phase 1：条目 CRUD + BM25 搜索 + Skill 草稿手动创建/审核
- Phase 2：文档导入（文件上传/文件夹扫描/URL抓取）+ SSE 进度 + 双层架构（Document + Chunk）
- Phase 3：文档管理层

**缺失环节**：文档导入 → chunks 入库后，没有自动分析和推荐生成 Skill 的能力。用户必须手动创建 SkillDraft，无法利用已有知识条目的聚合价值。

**目标**：实现"导入即推荐 → AI 生成骨架 → 人工补全 → 质量门禁 → 一键激活"的完整闭环，让知识条目的积累能自动沉淀为可执行的 Skill。

---

## 2. 完整流程设计

```
文档导入 & chunks 入库
       ↓
按 module × func_type 分组统计
       ↓
展示推荐面板（≥3条才推荐生成 Skill）
       ↓
用户选择分组 → 触发 AI 生成
       ↓
LLM 生成结构化骨架（含 ⚠️ 占位符）+ eval 草稿 + 冲突检测
       ↓
Skill 草稿编辑器（人工补全反例/版本/维护人/确认 eval）
       ↓
质量得分实时计算（7 维度 100 分制）
       ↓
满足门禁 → 提交审核
       ↓
审核通过 → 一键激活为正式 Skill
       ↓
EvoSkill 进化闭环衔接（任务反馈 → 知识更新 → Skill 迭代）
```

---

## 3. Skill 骨架模板

AI 生成的 Skill 草稿遵循以下结构化模板，⚠️ 标记表示需要人工补全：

```markdown
# [Skill 名称]

## 适用场景
[LLM 基于知识条目自动填充]
- 适用模块：xxx
- 适用业务类型：xxx
- 典型触发条件：xxx

## ⚠️ 不适用情况（请人工补充）
- [待人工确认]

## 核心处理方法
[LLM 基于知识条目聚合总结]

### 步骤 1：xxx
[具体操作内容]

### 步骤 2：xxx
[具体操作内容]

## 示例

### 正例
[LLM 从知识条目中提取/构造]

### ⚠️ 反例（待补充）
[需要人工提供不应该使用此 Skill 的场景]

## ⚠️ 版本与平台约束（待确认）
- Android 版本范围：[待确认]
- 芯片平台：[待确认]
- 适用 AOSP 分支：[待确认]

## 注意事项
[LLM 填充]

## 维护信息
- ⚠️ 维护人：[待指定]
- 生成来源：知识库条目 [entry_ids]
- 生成时间：[自动填充]
```

---

## 4. 质量评分体系（7 维度 100 分制）

| 维度 | 分值 | 评分规则 | 强制项 |
|------|------|----------|--------|
| 结构完整性 | 20 | 所有 section 都有实质内容（≥50字），无空 section | |
| 不适用情况 | 15 | ⚠️ 占位符已替换为具体描述（≥2条） | |
| 版本范围 | 20 | 明确的 Android 版本/芯片平台约束 | ✅ 强制 |
| eval 用例 | 25 | 至少 2 个 eval case（含输入/期望输出/判定标准） | ✅ 强制 |
| 无冲突 | 10 | 与现有 Skill 无功能重叠冲突 | |
| 维护人 | 10 | 已指定具体维护人（非空） | |

**门禁规则**：
- 总分 ≥ 60 分方可提交审核
- 强制项（版本范围 + eval 用例）未填写时，禁止提交审核（即使总分达标）
- 得分 < 60 时界面显示具体缺失项和改进建议

---

## 5. 冲突检测机制

生成 Skill 草稿时自动检测：

1. **功能重叠检测**：对比现有已激活 Skill，如果 module + func_type 相同且内容相似度 > 60%（BM25 交叉搜索），标记为"可能冲突"
2. **版本范围冲突**：如果两个 Skill 覆盖相同版本范围且处理相同问题域，提示合并建议
3. **关键词重叠**：keywords 重叠率 > 70% 时警告

冲突结果附加在 SkillDraft 中，审核时展示给审核人参考。

---

## 6. 数据模型变更

### 6.1 SkillDraft 新增字段

```typescript
interface SkillDraft {
  // ... 现有字段 ...
  
  // ─── Phase 4 新增 ───────────────────────────────
  
  /** AI 生成的 eval 用例草稿 */
  eval_cases?: EvalCase[]
  
  /** 7维质量评分（实时计算） */
  quality_score?: QualityScore
  
  /** 冲突检测结果 */
  conflicts?: ConflictResult[]
  
  /** Skill 骨架模板版本 */
  template_version?: string
  
  /** 人工编辑记录 */
  edit_history?: EditRecord[]
  
  /** 版本约束（从⚠️占位符提取为结构化数据） */
  version_constraints?: VersionConstraint
  
  /** 指定维护人 */
  maintenance_owner?: string
  
  /** 不适用情况列表 */
  exclusion_cases?: string[]
}

interface EvalCase {
  id: string
  title: string
  input: string                     // 输入场景描述
  expected_output: string           // 期望的 Skill 输出/行为
  judgment_criteria: string         // 判定标准（pass/fail 依据）
  source: 'ai_generated' | 'human' // 来源：AI 草稿 or 人工添加
  status: 'draft' | 'confirmed'    // 是否经过人工确认
}

interface QualityScore {
  total: number                     // 总分 0-100
  structure: number                 // 结构完整性 0-20
  exclusions: number                // 不适用情况 0-15
  version_range: number             // 版本范围 0-20
  eval_cases: number                // eval 用例 0-25
  no_conflict: number               // 无冲突 0-10
  owner: number                     // 维护人 0-10
  pass_gate: boolean                // 是否通过门禁
  blocking_reasons: string[]        // 未通过原因
}

interface ConflictResult {
  conflicting_skill_id: string
  conflicting_skill_name: string
  overlap_type: 'function' | 'version' | 'keyword'
  similarity_score: number
  suggestion: string                // 合并/区分建议
}

interface EditRecord {
  timestamp: string
  editor: string
  field: string
  old_value?: string
  new_value?: string
}

interface VersionConstraint {
  android_versions?: string[]       // e.g. ["Android 12", "Android 13", "Android 14"]
  chipset_platforms?: string[]      // e.g. ["MT6893", "MT6983"]
  aosp_branches?: string[]          // e.g. ["android-13.0.0_r1"]
}
```

---

## 7. 后端 API 接口设计

### 7.1 新增接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/tahp/knowledge/skill-suggestions` | 基于当前所有条目，按 module×func_type 分组统计，返回可推荐生成 Skill 的分组 |
| POST | `/api/tahp/knowledge/skill-drafts/generate` | 触发 AI 生成 Skill 骨架 + eval 草稿（接受 entry_ids 或 module+func_type） |
| GET | `/api/tahp/knowledge/skill-drafts/:draftId` | 获取单个草稿详情（含 eval_cases、quality_score、conflicts） |
| PUT | `/api/tahp/knowledge/skill-drafts/:draftId` | 更新草稿内容（人工编辑）+ 重新计算质量得分 |
| POST | `/api/tahp/knowledge/skill-drafts/:draftId/eval-cases` | 添加/更新 eval 用例 |
| GET | `/api/tahp/knowledge/skill-drafts/:draftId/quality` | 获取实时质量评分 |
| POST | `/api/tahp/knowledge/skill-drafts/:draftId/check-conflicts` | 手动触发冲突检测 |

### 7.2 接口参数详设

#### GET /api/tahp/knowledge/skill-suggestions

**响应：**
```json
{
  "suggestions": [
    {
      "module": "telephony",
      "func_type": "bug_analysis",
      "entry_count": 8,
      "entry_ids": ["kb-xxx", "kb-yyy", ...],
      "avg_confidence": 0.85,
      "recommended": true,
      "reason": "8 条相关知识条目，置信度 0.85，建议生成 Skill",
      "suggested_skill_name": "Telephony Bug 分析技能",
      "existing_skill_count": 1,
      "existing_skills": ["telephony-ril-debug"]
    }
  ],
  "total_groups": 6,
  "recommended_count": 3
}
```

#### POST /api/tahp/knowledge/skill-drafts/generate

**请求：**
```json
{
  "module": "telephony",
  "func_type": "bug_analysis",
  "entry_ids": ["kb-xxx", "kb-yyy"],
  "skill_name": "自定义名称（可选）",
  "generated_by": "user_name"
}
```

**响应：**
```json
{
  "draft": { /* SkillDraft 完整对象 */ },
  "eval_cases": [ /* EvalCase[] */ ],
  "conflicts": [ /* ConflictResult[] */ ],
  "quality_score": { /* QualityScore */ }
}
```

**生成逻辑**（后端实现）：
1. 从 entry_ids 加载所有知识条目内容
2. 按模板结构拼接 prompt，调用配置的 LLM（复用 tahp-run 中的 LLM 调用能力）
3. 解析 LLM 返回，填入 SkillDraft.content
4. 同步生成 2-3 个 eval case 草稿
5. 执行冲突检测（BM25 交叉搜索现有 Skill）
6. 计算初始质量得分
7. 持久化 SkillDraft

#### PUT /api/tahp/knowledge/skill-drafts/:draftId

**请求：**
```json
{
  "content": "更新后的 Skill 内容",
  "maintenance_owner": "张三",
  "exclusion_cases": ["不适用于 Android 11 以下"],
  "version_constraints": {
    "android_versions": ["Android 12", "Android 13"],
    "chipset_platforms": ["MT6893"]
  }
}
```

每次更新后自动重新计算 quality_score 并返回。

---

## 8. 前端 UI 交互方案

### 8.1 整体布局

在现有 KnowledgeBaseView 的 Tab 体系中新增 **"Skill 工坊"** Tab（或复用现有"Skill 草稿"Tab 并增强）：

```
知识库管理
├── 条目管理（现有）
├── 文档导入（现有）
├── 语义搜索（现有）
├── 文档管理（现有）
└── Skill 工坊（新增/增强）★
    ├── 推荐面板 — 展示可生成 Skill 的分组
    ├── 草稿列表 — 管理所有 SkillDraft
    └── 编辑器 — 结构化编辑 + 质量面板
```

### 8.2 推荐面板 UI

**触发时机**：
- 文档导入完成后，自动显示推荐提示（如果有新的推荐分组）
- Skill 工坊 Tab 打开时，顶部始终显示推荐卡片

**卡片设计**：
```
┌─────────────────────────────────────────────────────────────┐
│ 💡 推荐生成 Skill                                           │
├─────────────────────────────────────────────────────────────┤
│ ┌───────────────────┐ ┌───────────────────┐                │
│ │ telephony          │ │ kernel-driver     │                │
│ │ bug_analysis       │ │ code_adaptation   │                │
│ │ 8 条知识条目       │ │ 5 条知识条目       │                │
│ │ 置信度 0.85        │ │ 置信度 0.78        │                │
│ │ [✨ 生成 Skill]    │ │ [✨ 生成 Skill]    │                │
│ └───────────────────┘ └───────────────────┘                │
│                                                             │
│ ⚠️ power-mgmt / bug_analysis (2条，暂不推荐)               │
└─────────────────────────────────────────────────────────────┘
```

### 8.3 Skill 草稿编辑器 UI

点击"生成 Skill"或打开已有草稿时，进入结构化编辑器：

```
┌─────────────────────────────────────────────────────────────────────┐
│ Skill 编辑器 — telephony-bug-analysis-skill                         │
├───────────────────────────────────┬─────────────────────────────────┤
│                                   │                                 │
│ [Markdown 编辑区]                  │  质量得分面板                    │
│                                   │  ┌─────────────────────────┐    │
│ # Telephony Bug 分析技能           │  │ 总分：72/100              │    │
│                                   │  │ ━━━━━━━━━━━━━━━━━━ 72%    │    │
│ ## 适用场景                        │  │                           │    │
│ [编辑内容...]                      │  │ ✅ 结构完整性：18/20      │    │
│                                   │  │ ⚠️ 不适用情况：8/15       │    │
│ ## ⚠️ 不适用情况                   │  │ ❌ 版本范围：0/20 (强制)  │    │
│ [需要补充...]                      │  │ ⚠️ eval用例：15/25       │    │
│                                   │  │ ✅ 无冲突：10/10          │    │
│ ## 核心处理方法                    │  │ ❌ 维护人：0/10           │    │
│ [编辑内容...]                      │  │                           │    │
│                                   │  │ 🚫 不可提交审核            │    │
│ ## 示例                           │  │ 原因：版本范围未填写       │    │
│ ### 正例                          │  └─────────────────────────┘    │
│ [编辑内容...]                      │                                 │
│                                   │  冲突检测                        │
│ ### ⚠️ 反例（待补充）              │  ┌─────────────────────────┐    │
│ [需要补充...]                      │  │ ℹ️ 未发现冲突             │    │
│                                   │  └─────────────────────────┘    │
│ ## ⚠️ 版本与平台约束               │                                 │
│ [表单输入区]                       │  Eval 用例                      │
│ Android版本: [□12 □13 ☑14]       │  ┌─────────────────────────┐    │
│ 芯片平台:   [MT6893, ...]         │  │ Case 1: RIL 崩溃分析     │    │
│                                   │  │ 状态: AI草稿 [确认]       │    │
│ ## 维护信息                        │  │ Case 2: VoLTE 注册失败   │    │
│ 维护人: [___________]             │  │ 状态: 已确认 ✓            │    │
│                                   │  │ [+ 添加用例]              │    │
├───────────────────────────────────┴─────────────────────────────────┤
│ [保存草稿]  [重新生成]  [提交审核 🔒]  [取消]                        │
└─────────────────────────────────────────────────────────────────────┘
```

### 8.4 导入完成后的推荐提示

文档导入 Job 完成（save 后）时，如果新入库的 chunks 使某个分组达到推荐阈值（≥3条），在导入结果区域下方显示提示：

```
┌─────────────────────────────────────────────────────────────┐
│ ✅ 导入完成！已保存 12 个知识条目                             │
│                                                             │
│ 💡 新发现：telephony/bug_analysis 分组已有 8 条知识，         │
│    建议生成 Skill 以便 AI 执行时使用                          │
│    [前往 Skill 工坊 →]                                      │
└─────────────────────────────────────────────────────────────┘
```

---

## 9. LLM 生成 Prompt 设计

```
你是 TAHP 平台的 Skill 生成助手。请基于以下知识条目，生成一个结构化的 Skill 文档。

## 输入知识条目

{entries_content}

## 上下文信息
- 模块：{module}
- 业务类型：{func_type}
- 条目数量：{entry_count}

## 输出要求

请按以下模板结构输出：

### 适用场景
[基于知识条目总结适用场景，具体到模块、业务类型、典型触发条件]

### 不适用情况
[基于知识条目推断，但标注"待人工确认"，至少列出 2 项]

### 核心处理方法
[将知识条目中的关键步骤和方法提炼为可操作的步骤列表]

### 正例
[从知识条目中选取最典型的 1-2 个案例作为正例]

### 反例（待补充）
[如果知识条目中有失败案例可提取，否则标注"待人工补充"]

### 版本与平台约束
[如果知识条目中提到了版本信息则提取，否则标注"待确认"]

### 注意事项
[提炼知识条目中的注意事项和陷阱]

---

同时请输出 2-3 个 eval 用例，格式：
EVAL_CASE_START
title: [用例标题]
input: [输入场景描述]
expected_output: [期望输出/行为]
judgment_criteria: [pass/fail 判定标准]
EVAL_CASE_END
```

---

## 10. 开发计划

### Step 1：后端数据模型升级 + 推荐接口（0.5天）

1. 扩展 SkillDraft 接口，新增 eval_cases、quality_score、conflicts 等字段
2. 实现 `GET /api/tahp/knowledge/skill-suggestions` 接口（分组统计逻辑）
3. 实现质量得分计算函数 `calculateQualityScore(draft)`
4. 实现冲突检测函数 `detectConflicts(draft, existingSkills)`

### Step 2：LLM 生成接口（0.5天）

1. 实现 `POST /api/tahp/knowledge/skill-drafts/generate`
2. 复用 tahp-run 的 LLM 调用能力（或直接调用配置的 API endpoint）
3. Prompt 拼接 + 响应解析（提取 Skill 内容和 eval cases）
4. 持久化生成结果

### Step 3：草稿编辑 + eval 管理接口（0.5天）

1. 实现 `PUT /api/tahp/knowledge/skill-drafts/:draftId`（带质量重算）
2. 实现 `POST /api/tahp/knowledge/skill-drafts/:draftId/eval-cases`
3. 实现 `GET /api/tahp/knowledge/skill-drafts/:draftId/quality`
4. 更新现有审核接口：增加门禁校验（强制项必须通过）

### Step 4：前端 Skill 工坊 Tab + 推荐面板（1天）

1. 新增 Skill 工坊 Tab（或增强现有 Skill 草稿 Tab）
2. 实现推荐面板组件（调用 skill-suggestions 接口）
3. 实现"生成 Skill"按钮 + loading 状态
4. 导入完成后的推荐提示组件

### Step 5：前端 Skill 编辑器 + 质量面板（1天）

1. 实现结构化 Markdown 编辑器（左右分栏）
2. 实现质量得分面板（实时计算 + 可视化）
3. 实现版本约束表单（多选 Android 版本 + 芯片输入）
4. 实现 eval 用例管理面板（添加/编辑/确认）
5. 冲突检测结果展示

### Step 6：前端审核增强 + 门禁校验（0.5天）

1. 提交审核按钮增加门禁校验（灰化 + tooltip 显示原因）
2. 审核界面展示质量得分 + 冲突信息
3. 激活后的反馈提示

### Step 7：集成测试 + 端到端验证（0.5天）

1. 后端接口单元测试
2. 前端组件联调
3. 完整流程验证：导入文档 → 推荐 → 生成 → 编辑 → 审核 → 激活
4. 边界条件：0 条目、冲突场景、LLM 超时等

---

## 11. 技术依赖与风险

| 风险项 | 影响 | 缓解措施 |
|--------|------|----------|
| LLM 调用不可用 | 无法生成骨架 | 提供手动创建入口作为 fallback |
| LLM 输出格式不稳定 | 解析失败 | 宽松解析 + 重试 + 手动编辑兜底 |
| 大量条目时性能 | 推荐接口慢 | 内存缓存 + 增量更新 |
| 冲突检测误报 | 用户困惑 | 仅作为"参考"提示，不阻塞 |

---

## 12. 与 EvoSkill 进化闭环的衔接

```
知识库 → Skill 草稿 → 激活
                         ↓
                   AI 任务执行使用 Skill
                         ↓
                   任务反馈（成功/失败）
                         ↓
              feedback → 知识条目更新 usage_count
                         ↓
              达到阈值 → 建议更新 Skill
                         ↓
              EvoSkill 自动生成更新版 Skill 草稿
                         ↓
              人工审核 → 替换旧版 Skill
```

当前 Phase 4 聚焦"知识库 → Skill"这一段。EvoSkill 闭环在后续 Phase 中实现，但数据模型预留了 `edit_history`、`usage_count`、`last_used_in_task` 等字段以支撑。

---

## 附录：现有代码资产盘点

| 文件 | 已有能力 | Phase 4 扩展点 |
|------|----------|----------------|
| `knowledge.ts` (server) | SkillDraft CRUD + 审核 + 激活 | 新增 generate/suggestions/quality/conflicts |
| `skills.ts` (server) | Adapt Skill 创建/删除/列表 | 冲突检测需调用 scanAdaptSkills() |
| `knowledge.ts` (client API) | SkillDraft 接口定义 + CRUD | 新增 generate/suggestions/eval 接口 |
| `KnowledgeBaseView.vue` | 5个Tab + 导入 + 搜索 | 新增 Skill 工坊 Tab |
| `tahp-run.ts` (server) | LLM 调用能力 | 复用于 Skill 生成 |
