# 知识库转 Skill — 评审结论与落地步骤

> 评审日期：2026-05-28  
> 基于：knowledge-to-skill-design.md v1.0

---

## 评审要点

### 1. 与现有代码衔接评估 ✅

| 评估项 | 结论 |
|--------|------|
| SkillDraft 数据模型 | 现有字段向后兼容，新字段全部 optional，无破坏性变更 |
| 审核激活逻辑 | knowledge.ts L1106-1159 已有完整激活逻辑（写入 skills/.claude/skills/），可复用 |
| 冲突检测 | skills.ts 的 `scanAdaptSkills()` 可直接复用获取已激活 Skill 列表 |
| LLM 调用 | `handle-api-run.ts` 中 `resolveGatewayUpstream()` 提供完整的 LLM 配置解析，可抽取为独立的 `callLLM()` 工具函数 |
| JSON 解析 | `llm-json.ts` 已有 `extractJSON()`、`fixLLMJSON()` 等容错解析能力，可直接复用 |
| 文件存储 | 知识库使用 `.kb-data/skill-drafts/` 目录 + JSON 文件持久化，扩展字段无需迁移 |

### 2. 方案简化建议

| 原方案 | 简化建议 | 理由 |
|--------|----------|------|
| 7维独立评分函数 | 内联到 PUT handler 中实时计算 | 评分逻辑简单，不需要独立接口 |
| 独立 quality 接口 | 合并到 GET :draftId 响应中 | 减少前端请求数 |
| 独立 check-conflicts 接口 | 合并到 generate 和 PUT 中自动执行 | 用户不需要手动触发 |
| edit_history 数组 | Phase 4 暂不实现 | 不是核心流程，后续增加 |

### 3. LLM 调用方案确认

采用 **独立的轻量 LLM 调用函数**，从 `resolveGatewayUpstream` 获取配置后直接调 OpenAI-compatible `/v1/chat/completions`：

```typescript
// 新文件：packages/server/src/services/tahp/llm-caller.ts
export async function callTahpLLM(systemPrompt: string, userContent: string): Promise<string>
```

不走完整的 chat session 流程（无需 session store、history compression 等），只做单次 prompt → response。

---

## 落地执行步骤（精简为 5 步）

### Step 1：后端核心 — LLM 调用 + 数据模型 + 3个新接口

**文件变更：**
- **新建** `packages/server/src/services/tahp/llm-caller.ts` — 轻量 LLM 单次调用
- **修改** `packages/server/src/routes/tahp/knowledge.ts`：
  - 扩展 SkillDraft interface（新增 eval_cases, quality_score, conflicts 等）
  - 新增 `GET /api/tahp/knowledge/skill-suggestions`
  - 新增 `POST /api/tahp/knowledge/skill-drafts/generate`
  - 修改 `PUT /api/tahp/knowledge/skill-drafts/:draftId`（支持编辑 + 质量重算）
  - 修改审核接口（增加门禁校验）
  - 新增质量评分计算函数 + 冲突检测函数

### Step 2：前端 API 层

**文件变更：**
- **修改** `packages/client/src/api/tahp/knowledge.ts`：
  - 新增接口类型：EvalCase, QualityScore, ConflictResult, VersionConstraint
  - 扩展 SkillDraft 接口
  - 新增 API 函数：getSkillSuggestions, generateSkillDraft, updateSkillDraft

### Step 3：前端 Skill 工坊 Tab — 推荐面板 + 生成

**文件变更：**
- **修改** `packages/client/src/views/tahp/KnowledgeBaseView.vue`：
  - 新增"Skill 工坊"Tab（或增强现有 Skill 草稿 Tab）
  - 推荐卡片组件
  - "生成 Skill"按钮 + loading 态
  - 草稿列表增强（显示 quality_score 徽章）

### Step 4：前端 Skill 编辑器 + 质量面板

**文件变更：**
- **修改** `packages/client/src/views/tahp/KnowledgeBaseView.vue`：
  - 左右分栏编辑器（Markdown + 质量面板）
  - 版本约束表单
  - Eval 用例管理区
  - 提交审核门禁（按钮灰化 + 原因提示）

### Step 5：联调验证 + 导入后推荐提示

**文件变更：**
- **修改** `packages/client/src/views/tahp/KnowledgeBaseView.vue`：
  - 导入完成后检查推荐条件，显示提示
- **端到端测试**：导入 → 推荐 → 生成 → 编辑 → 审核 → 激活

---

## 执行确认

以上 5 步按顺序依次执行。每步完成后进行编译检查（`vue-tsc -b && tsc --noEmit -p packages/server/tsconfig.json`），确保无类型错误后再进入下一步。

开始执行 Step 1。
