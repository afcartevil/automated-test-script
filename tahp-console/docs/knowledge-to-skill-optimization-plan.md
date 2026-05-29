# 知识库转 Skill 优化计划

> 版本：v1.1 | 日期：2026-05-28  
> 范围：tahp-console 知识库 → Skill 工坊完整优化  
> 前置文档：[knowledge-to-skill-design.md](./knowledge-to-skill-design.md)

---

## 一、现状问题全景

通过代码审查（`knowledge.ts`/`KnowledgeBaseView.vue`/`skills.ts`），梳理出以下四类问题：

| # | 问题 | 影响 | 严重级别 |
|---|------|------|---------|
| P1 | `code_adaptation`/`version_adaptation`/`carrier_porting` 被压缩为同一个 `"AI自动化适配"` | Skill frontmatter 丢失细分信息；skill-suggestions 过滤失效 | **P0** |
| P2 | 前端 `MODULE_OPTIONS` 缺少"内核(kernel)"模块 | 内核模块条目无法正确分类 | **P0** |
| P3 | 同一文档重复生成 Skill 无任何拦截 | 产生大量重复 Skill 草稿，质量混乱 | **P0** |
| P4 | 生成过程无进度反馈，体验差 | 用户不知道 LLM 是否在工作（超时120s） | **P1** |
| P5 | 相似度检测仅基于 entry_id Jaccard，重新导入的文档检测失效 | 内容相同的文档绕过相似检测 | **P1** |
| P6 | 融合推荐只告知"有相似"，未说明"融合的收益" | 用户不知选哪个目标，倾向于强制新建 | **P1** |
| P7 | 已激活 Skill 无法参与融合 | 已有生产 Skill 不能被新知识增强 | **P2** |

---

## 二、技术约束说明（影响实现方式）

在开始实现前，需确认以下技术约束：

### 2.1 LLM 调用为非流式
`callTahpLLM`（`llm-caller.ts`）是**一次性返回完整文本**的同步调用（Anthropic/OpenAI-compat 均如此），无真正的 streaming。  
**影响**：生成进度的 SSE 更新只能在 LLM 调用前后插桩（模拟分阶段进度），而非真正字符级流式推送。

### 2.2 `crypto.createHash` 需补充导入
`knowledge.ts` 目前只导入 `randomUUID`，内容指纹需要额外引入 `createHash`：
```typescript
import { randomUUID, createHash } from 'crypto'
```

### 2.3 内存 Map 无持久化
`importJobs`/将新增的 `skillGenJobs` 均为内存 Map，服务重启后丢失。需设计 TTL 自动清理（避免内存泄漏），且前端需处理 SSE 连接失效的降级。

### 2.4 SSE EventSource 的 Base URL
前端 `subscribeGenerateProgress` 使用 `EventSource`，需使用运行时可用的 baseURL（不能依赖编译时 `import.meta.env`），建议读取 `window.location.origin` 或通过 axios 实例的 `baseURL` 推导。

---

## 三、实施计划

### Phase 1：分类映射体系修复 ⭐ P0（估时 0.5天）

**目标**：建立 raw → display 一对一映射，保留细分信息，消除多对一压缩。

#### 1.1 改动范围

| 文件 | 改动类型 | 说明 |
|------|----------|------|
| `server/src/routes/tahp/knowledge.ts` | 替换映射表 + 补充辅助函数 | 核心改动 |
| `server/src/controllers/hermes/skills.ts` | 同步更新 normalize 函数 | 保持一致性 |
| `client/src/views/tahp/KnowledgeBaseView.vue` | 补充 MODULE_OPTIONS 内核项 + 更新 display 映射 | 前端对齐 |

#### 1.2 分类规范

**功能类型（func_type）**：

| raw 存储值 | display 展示标签 | 大类（category） |
|-----------|-----------------|-----------------|
| `bug_analysis` | Bug分析 | **AI故障分析** |
| `code_adaptation` | 代码适配 | **AI自动化适配** |
| `version_adaptation` | 版本适配 | **AI自动化适配** |
| `carrier_porting` | 运营商移植 | **AI自动化适配** |
| `ai_self_check` | AI自检 | **AI自检工具** |
| `self_check` | 自检工具 | **AI自检工具** |
| `other` | 其他 | **其他** |

**业务模块（module）**：

| raw 存储值 | display 展示标签 |
|-----------|-----------------|
| `telephony` | 通信 |
| `kernel-driver` | 驱动 |
| `kernel` | 内核 |
| `power-mgmt` | 功耗 |
| `shared` / `common` | 通用 |
| `custom` | 用户自定义 |

#### 1.3 frontmatter 存储策略（解决精度丢失）

激活 Skill 时，frontmatter 同时写入 display 值和 raw 值：
```yaml
module: "通信"           # display，供 UI 展示
module_raw: "telephony"  # raw，供程序筛选
func_type: "代码适配"    # display
func_type_raw: "code_adaptation"  # raw，保留细分
funcType: "代码适配"     # camelCase（scanner 读取）
category: "AI自动化适配" # 大类分组
group: "通信"
```

#### 1.4 关键实现细节

- `normFuncType(v)` 仍然用于 UI 展示，新增 `normFuncTypeRaw(v)` 用于存储
- `getFuncTypeCategory(v)` 用于 Skill 侧边栏大类分组
- 前端 `FUNC_TYPE_SHORT` 保留 raw → display 映射（不变），`MODULE_OPTIONS` 补充内核项

---

### Phase 2：文档级重复检测 ⭐ P0（估时 1天）

**目标**：在 LLM 调用前插入三层防御，彻底解决重复生成问题。

#### 2.1 三层防御流程图

```
用户点击"生成 Skill"
         │
         ▼
┌─── 第一层：文档溯源检测 ─────────────────────────────────────┐
│  - 从 entry_ids 反查 source_document_id                      │
│  - 计算条目内容 content_fingerprint（SHA256前16位）           │
│  - 扫描所有未拒绝草稿的 source_document_ids/fingerprint       │
│  命中 → 返回 duplicate_detected=true，前端展示重复弹窗        │
└─────────────────────────────────────────────────────────────┘
         │ 未命中
         ▼
┌─── 第二层：内容语义相似检测 ────────────────────────────────┐
│  - 现有 checkSkillSimilarity 接口已有 Jaccard(entry_ids)     │
│  - 新增：条目内容 BM25 token 重叠率（覆盖"重新导入"场景）     │
│  - contentSim > 0.5 → 提升相似结果的 tier                    │
│  命中 → 现有相似度弹窗（已有），补充内容语义匹配原因           │
└─────────────────────────────────────────────────────────────┘
         │ 未命中
         ▼
┌─── 第三层：结构级融合推荐 ──────────────────────────────────┐
│  - 同 module × func_type 已有 Skill（draft 或 activated）    │
│  - 计算融合价值（新增主题词数量 + 可增强章节）                │
│  命中且 match_score > 0.2 → 推荐融合弹窗（非强制）           │
└─────────────────────────────────────────────────────────────┘
         │ 未命中（或用户选择新建）
         ▼
    LLM 生成新 Skill
```

#### 2.2 SkillDraft 新增字段

```typescript
interface SkillDraft {
  // ... 现有字段 ...

  /** 来源文档ID列表（从 entry.source_document_id 聚合） */
  source_document_ids?: string[]

  /** 内容指纹：sorted(entry.content).join('\n').sha256.slice(0,16) */
  content_fingerprint?: string

  /** 用户重复决策记录（防止同一场景重复弹窗） */
  duplicate_decisions?: Array<{
    decision: 'force_create' | 'view_existing' | 'merge'
    target_id?: string
    decided_at: string
  }>
}
```

#### 2.3 新增 API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/tahp/knowledge/skill-drafts/check-duplicate` | 文档级重复检测（独立接口，可被前端在生成前主动调用） |
| `POST` | `/api/tahp/knowledge/skill-drafts/duplicate-decision` | 记录用户对重复的处理决策 |
| `POST` | `/api/tahp/knowledge/skill-drafts/recommend-merge-target` | 智能融合目标推荐 |

> `/generate` 接口内部也会集成检测，但独立接口方便前端提前预检。

#### 2.4 重复检测弹窗 UI 设计

```
┌─────────────────────────────────────────────────────────────┐
│ ⚠️  检测到文档重复                                           │
├─────────────────────────────────────────────────────────────┤
│ 该批知识条目来自于已经生成过 Skill 的文档：                    │
│                                                             │
│  • "通信 Bug分析 Skill"  [草稿 · 2026-05-20]               │
│    匹配方式：文档来源匹配                                     │
│    [📋 查看该草稿]   [➕ 增量更新到该草稿]                    │
│                                                             │
│  • "kb-skill-telephony-bug-xxx"  [已激活 · 2026-05-18]     │
│    匹配方式：内容指纹匹配                                     │
│    [📋 查看已有]   [🔄 生成升级草案]                         │
│                                                             │
│                            [🆕 仍要创建新 Skill]            │
└─────────────────────────────────────────────────────────────┘
```

#### 2.5 用户决策处理

| 用户选择 | 行为 | 备注 |
|----------|------|------|
| 查看草稿/已有 | 打开编辑器（只读或编辑模式） | 不触发新生成 |
| 增量更新到已有草稿 | 调用 `/merge` 接口融合新条目 | 草稿 → 草稿融合 |
| 生成升级草案（针对已激活） | 以已激活 Skill 内容为基础创建新草稿，再融合 | 见 Phase 4 |
| 仍要创建新 Skill | 记录决策后绕过检测，继续生成 | 记录 `force_create` |

---

### Phase 3：生成过程可视化 ⭐ P1（估时 1天）

**目标**：将"黑箱等待"改为分步可视化进度，明确每一步的状态。

#### 3.1 技术方案：SSE Job（复用已有基础设施）

与 `importJobs` 相同的设计模式，新增 `skillGenJobs`：

```typescript
interface SkillGenJob {
  id: string
  status: 'running' | 'completed' | 'error' | 'cancelled'
  // 当前阶段
  stage: 'init' | 'duplicate_check' | 'similarity_check' | 'llm_generate'
        | 'eval_extract' | 'quality_score' | 'done' | 'error'
  progress: number  // 0-100
  message: string   // 当前阶段说明文字
  result?: {
    draft?: SkillDraft
    duplicate_detected?: boolean
    duplicate_drafts?: DuplicateInfo[]
    similar_skills?: SimilarSkillItem[]
    llm_error?: string
  }
  created_at: string
  ttl_expires_at: string  // 30分钟后自动清理
}
```

#### 3.2 新增接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/tahp/knowledge/skill-drafts/generate-stream` | 启动异步生成任务，返回 jobId |
| `GET` | `/api/tahp/knowledge/skill-drafts/generate-stream/:jobId` | SSE 订阅进度 |

**注意**：原 `POST /generate` 接口**保留不变**，作为不需要进度反馈时的同步调用方式（兼容现有测试脚本和 MCP 工具调用场景）。

#### 3.3 异步生成函数 `runSkillGenerationStream` 执行步骤

```
Step 0: 加载条目               → progress: 8,  stage: 'init'
Step 1: 文档级重复检测          → progress: 20, stage: 'duplicate_check'
         命中 → completed(duplicate_detected=true), 不继续
Step 2: 内容相似度检索          → progress: 35, stage: 'similarity_check'
         命中 → completed(similar_skills=[...]), 不继续
Step 3: LLM 调用前              → progress: 45, stage: 'llm_generate', msg: '正在调用 LLM...'
Step 4: callTahpLLM()          (阻塞，最长120s)
Step 5: LLM 响应解析            → progress: 65, stage: 'llm_generate', msg: '解析 LLM 输出...'
         失败 → 降级模板，记录 llm_error
Step 6: 解析 eval 用例          → progress: 78, stage: 'eval_extract'
Step 7: 计算质量评分 + 冲突检测 → progress: 90, stage: 'quality_score'
Step 8: 持久化 SkillDraft       → progress: 98
Step 9: 完成                   → progress: 100, stage: 'done', status: 'completed'
```

> **重要**：因 `callTahpLLM` 非流式，Step 3 → Step 5 之间无真正的字符推送。
> 前端需在 `llm_generate` 阶段展示 animated spinner + 消息，不展示假进度条增量。

#### 3.4 SSE job TTL 清理

在 `knowledge.ts` 模块初始化时启动定时器：
```typescript
// 每5分钟清理一次超过30分钟的 job
setInterval(() => {
  const now = Date.now()
  for (const [id, job] of skillGenJobs) {
    const ttl = new Date(job.ttl_expires_at).getTime()
    if (now > ttl) {
      skillGenJobs.delete(id)
      skillGenListeners.delete(id)
    }
  }
}, 5 * 60 * 1000)
```

#### 3.5 前端进度弹窗 UI

```
┌─────────────────────────────────────────────────────────────────┐
│  🚀 正在生成 Skill：通信 / Bug分析                                │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 45%                    │
│  正在调用 LLM 生成 Skill 文档...                                  │
│─────────────────────────────────────────────────────────────────│
│  ✅ 1. 文档重复检测     完成（未发现重复）                          │
│  ✅ 2. 相似 Skill 检索  完成（未发现相似）                          │
│  ⟳  3. AI 生成骨架     进行中（LLM 响应中，最长等待 120s）         │
│  ⏳ 4. 生成 Eval 用例   等待                                      │
│  ⏳ 5. 质量评分计算     等待                                       │
│─────────────────────────────────────────────────────────────────│
│                                              [取消]              │
└─────────────────────────────────────────────────────────────────┘
```

#### 3.6 前端处理完成信号

`job.status === 'completed'` 时，根据 `result` 内容分支处理：

```
result.duplicate_detected == true  → 关闭进度弹窗 → 打开重复检测弹窗
result.similar_skills.length > 0   → 关闭进度弹窗 → 打开相似度弹窗
result.draft 存在                  → 关闭进度弹窗 → 打开 Skill 编辑器
                                      (附带 llm_error 警告)
```

#### 3.7 前端 SSE 降级处理

若 `EventSource` 连接在 130s 内无 `completed` 事件（LLM 超时+网络延迟），前端需：
1. 显示超时提示
2. 提供"重新检查"按钮（`GET /generate-stream/:jobId` 拉取最新状态）

---

### Phase 4：智能融合推荐与已激活 Skill 增强 ⭐ P2（估时 0.5天）

**目标**：让用户清楚知道应该融合到哪个目标，以及融合的价值；支持已激活 Skill 的知识增强。

#### 4.1 融合推荐接口

`POST /api/tahp/knowledge/skill-drafts/recommend-merge-target`

**请求体**：
```json
{ "entry_ids": ["kb-xxx", "kb-yyy"], "module": "telephony", "func_type": "bug_analysis" }
```

**返回**（最多5个推荐）：
```json
{
  "recommendations": [
    {
      "target_id": "sd-abc123",
      "target_name": "通信 Bug分析 Skill",
      "target_type": "draft",
      "match_score": 0.82,
      "new_topics": ["RIL空指针", "VoLTE注册超时"],
      "new_topics_count": 5,
      "common_topics_count": 3,
      "estimated_quality_delta": +12,
      "reason": "可补充 5 个新知识主题，预估质量分提升 12 分",
      "can_merge": true       // draft 可直接融合
    },
    {
      "target_id": "kb-skill-telephony-bug-xxx",
      "target_name": "kb-skill-telephony-bug-xxx",
      "target_type": "activated",
      "match_score": 0.71,
      "new_topics_count": 3,
      "common_topics_count": 6,
      "estimated_quality_delta": +8,
      "reason": "已激活的生产 Skill，新建升级草案后融合",
      "can_merge": false,     // 已激活的不能直接融合，需先生成升级草案
      "upgrade_hint": "将以此 Skill 为基础生成升级草案"
    }
  ]
}
```

**推荐算法（无 LLM，纯本地计算）**：
```
new_topics_count  = entry关键词 中 不在 target.keywords 中的数量
common_topics_count = entry关键词 中 在 target.keywords 中的数量
match_score = (new_topics * 0.4 + common_topics * 0.3) / max(entry_keywords_count, 1)
```

#### 4.2 已激活 Skill 的"升级草案"流程

```
用户选择「生成升级草案」
    ↓
后端：读取已激活 Skill 的 SKILL.md 内容
    ↓
创建新 SkillDraft，初始 content = 已激活 Skill 的 body（去掉 frontmatter）
    generated_from_entries = 原 generated_from_entries + 新 entry_ids
    skill_id = 原 skill_id + "-v2-" + timestamp
    skill_name = 原名称 + " (增强版)"
    ↓
调用 /merge 接口执行 LLM 增量融合
    ↓
前端打开 Skill 编辑器（状态：草稿，含融合后内容）
    ↓
用户完善后走审核激活流程
（审核通过后：激活新 Skill，旧 Skill 目录保留不删除）
```

#### 4.3 融合推荐弹窗 UI

```
┌─────────────────────────────────────────────────────────────────┐
│  💡 发现已有相似 Skill，建议融合而非新建                            │
├────────────────────────────────────────────────────────────────┤
│  推荐融合目标 #1 ★★★★☆                                         │
│  📄 通信 Bug分析 Skill  [草稿]                                   │
│  可补充：RIL空指针、VoLTE注册超时 等 5 个新主题                   │
│  预估质量分提升：+12 分                                           │
│  [🔄 融合到此草稿]                                               │
│                                                                 │
│  推荐融合目标 #2 ★★★☆☆                                         │
│  ⚡ kb-skill-telephony-bug-xxx  [已激活]                         │
│  可补充 3 个新主题，将生成升级草案                                 │
│  [📝 生成升级草案]                                               │
│─────────────────────────────────────────────────────────────────│
│                                          [🆕 忽略，创建新 Skill] │
└─────────────────────────────────────────────────────────────────┘
```

---

## 四、完整改动文件清单

| 文件 | Phase | 改动类型 | 说明 |
|------|-------|---------|------|
| `server/routes/tahp/knowledge.ts` | 1+2+3+4 | **核心改动** | 映射表/检测函数/SSE/融合推荐 |
| `server/controllers/hermes/skills.ts` | 1 | 同步更新 | normalizeFuncType/normalizeModule |
| `server/services/tahp/llm-caller.ts` | 3 | 无需改动 | 已有能力够用 |
| `client/src/api/tahp/knowledge.ts` | 2+3+4 | 新增类型+函数 | SSE接口/重复检测/融合推荐 |
| `client/src/views/tahp/KnowledgeBaseView.vue` | 1+2+3+4 | **核心改动** | 弹窗/进度/分类选项 |

---

## 五、关键实现注意事项

### 5.1 Phase 1 注意事项
- `normFuncType` 改为一对一映射后，`skills.ts` 中已生成的 Skill（frontmatter 含 `"AI自动化适配"`）无法反推 raw 值——**这是历史数据问题，不影响新生成的 Skill**，无需迁移。
- 前端 `MODULE_OPTIONS` 加入 `{ label: '内核 (Kernel)', value: 'kernel' }` 后，需同步更新 `MODULE_SHORT` 和 `MODULE_COLOR`。

### 5.2 Phase 2 注意事项
- `createHash` 需从 `'crypto'` 导入（当前只导入了 `randomUUID`）。
- `source_document_ids` 需要在**文档导入保存**（`/import/jobs/:jobId/save`）时一并写入 entry，以确保后续能溯源。当前 entry 只有 `source_document_id`（单数），`source_document_ids` 是草稿级别的聚合字段。
- 重复检测查出结果后**不写入任何文件**，仅返回给前端。只有用户选择时才通过 `/duplicate-decision` 写入决策记录。
- `force_create` 的决策记录写在**已有草稿**上（作为"这个草稿的生成场景已被用户知晓"的标记），下次同一条目集合请求时通过 `can_force_create` 判断跳过弹窗。

### 5.3 Phase 3 注意事项
- `showDuplicateModal` 在前端需区分**变量名**（`ref(false)`）和**函数名**（`function showDuplicateModal()`），避免命名冲突，建议函数命名为 `openDuplicateModal`。
- `EventSource` 不支持设置请求头，若接口需要认证需通过 URL 参数传 token，或在前端项目框架中使用已封装的 SSE 工具类。
- SSE 断开后，若 job 仍在运行，下次重连时 `GET /:jobId` 会立即推送当前状态，前端无需重新发起生成请求。

### 5.4 Phase 4 注意事项
- 推荐算法中的 `extractKeywords` 函数仅基于正则提取中英文词，对于条目内容推荐时应直接读取 `entry.keywords` 字段（已由导入时计算），而非对 content 重新提取。
- 已激活 Skill 生成升级草案时，不删除原 Skill 目录（`skills/.claude/skills/<skillId>/`），两个版本共存，由用户或审核人决定是否替换。

---

## 六、测试验收标准

| 功能点 | 验收条件 |
|--------|---------|
| Phase 1：映射修复 | 激活一个代码适配 Skill，`SKILL.md` frontmatter 中 `func_type_raw` 为 `"code_adaptation"`，`func_type` 为 `"代码适配"` |
| Phase 2：重复检测-文档级 | 同一文档导入两次，第二次条目生成 Skill 时弹出重复检测弹窗，列出已有草稿 |
| Phase 2：重复检测-指纹级 | 内容相同但不同批次入库的条目，生成时同样被拦截 |
| Phase 2：force_create 不重复弹 | 选择"仍要创建新 Skill"后，同一批条目再次生成时不再弹出重复弹窗 |
| Phase 3：进度分步展示 | 点击生成后 500ms 内弹出进度弹窗，看到"文档重复检测"步骤 ✅ 完成 |
| Phase 3：LLM 阶段等待 | 在"AI 生成骨架"步骤看到 spinner 动画（非增量进度数字） |
| Phase 3：生成成功 | 完成后自动关闭进度弹窗，打开 Skill 编辑器 |
| Phase 4：融合推荐 | 存在相似草稿时，弹窗展示推荐卡片，含"可补充N个新主题"说明 |
| Phase 4：升级草案 | 对已激活 Skill 选择"生成升级草案"，产生新草稿，内容包含原 Skill 内容 |

---

## 七、实施顺序建议

```
Day 1 上午：Phase 1（映射修复 + 前端选项补全）
Day 1 下午：Phase 2 后端（重复检测函数 + 新增接口 + generate 接口集成）
Day 2 上午：Phase 2 前端（重复检测弹窗 + 决策记录）
Day 2 下午：Phase 3 后端（SSE job + generate-stream 接口）
Day 3 上午：Phase 3 前端（进度弹窗 UI + startGenerateSkill 改造）
Day 3 下午：Phase 4（融合推荐接口 + 升级草案 + 推荐弹窗 UI）
Day 4：     集成测试 + 边界条件验证 + 文档更新
```

---

## 八、不在本次范围内的事项

以下事项已识别，待后续 Phase 规划：
- LLM 真正流式输出（需 llm-caller.ts 支持 streaming）
- Skill 版本管理（激活 v2 后 v1 的归档策略）
- 多用户并发生成同一分组的锁机制
- EvoSkill 任务反馈自动触发 Skill 迭代建议
