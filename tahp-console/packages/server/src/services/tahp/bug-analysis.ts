/**
 * TAHP — AI Bug 分析编排（Agent 模式）
 *
 * 设计原则：
 *   - **所有 Bug 分析必须走 Claude Code Agent**（通过 hermes agent-bridge）
 *   - Agent 拥有完整 Skill / MCP 工具链（jira-mcp / transsion-harness / BSP 分析 skill）
 *   - **不允许降级到 BFF 直连 LLM**：若 agent 不可用或调用失败，任务直接失败
 *   - JIRA 信息由 Agent 自己用 Skill 拉取；BFF 只在 "预览 JIRA" 按钮和 JQL 候选枚举时使用 jira.ts
 *
 * 职责：
 *   - 维护 Bug 分析任务上下文（单条 / JQL 批量）
 *   - 把 Bug 任务投递到 Agent Bridge，监听并转发 tool.started / tool.completed / 文本 delta
 *   - 通过 TaskStream 推送 task.* 事件给前端实时显示
 *   - 支持"补充信息继续分析"（带前次上下文重跑）
 *
 * 报告落盘：
 *   reports/bug-analysis/<task-id>.json
 *
 * 任务日志：
 *   <appHome>/logs/bug-analysis/<task-id>.log（见 bug-analysis-logger.ts）
 *
 * 事件流（在 task-stream.ts 全局命名空间，前端通过 Socket.IO 订阅 /tahp-run）：
 *   task.started        启动
 *   task.phase          阶段切换（CONNECTING_AGENT / ANALYZING / GENERATING_REPORT）
 *   task.step           子步骤完成
 *   task.message        Agent 流式 chunk（level=stream）或一般日志
 *   task.skill_use      Agent 真实调用了 tool / skill（来自 tool.started 事件）
 *   task.tool_completed Agent tool 调用完成
 *   task.completed      完成 + 摘要
 *   task.failed         失败 + error
 *
 * 任务 ID 前缀:
 *   单条:  task-bug-<ts>-<rand>
 *   批量:  task-bugjob-<ts>-<rand> （父）+ task-bug-* （子）
 */
import { randomBytes } from 'crypto'
import { existsSync, mkdirSync, writeFileSync, readFileSync } from 'fs'
import { join } from 'path'
import { logger } from '../logger'
import { getTaskStream } from './task-stream'
import { tahpPaths } from './paths'
import {
  AgentBridgeClient,
  getAgentBridgeManager,
  type AgentBridgeChatStarted,
  type AgentBridgeOutput,
} from '../hermes/agent-bridge'
import { filterBridgeToolCallMarkupDelta } from '../hermes/run-chat/bridge-delta'
import {
  fetchIssue, searchJQL, parseIssueKey,
  type JiraIssue, type JiraIssueSummary, type JiraConfig,
} from './jira'
import { logBug, appendBugLog } from './bug-analysis-logger'

// ─── Agent Bridge 客户端（单例） ────────────────────────────────────────────
//
// 复用一个 AgentBridgeClient（短连接），交给每个 task 独立的 session_id。
// 任务结束后会 destroy(session) 释放 Agent Pool 资源。
//
// 超时设置较长（30 分钟）：考虑到 Agent 真正会跑日志下载等耗时操作。
const sharedBridgeClient = new AgentBridgeClient({ timeoutMs: 30 * 60_000 })

// ─── 类型定义 ────────────────────────────────────────────────────────────────

// 历史保留的模块类型：BFF 不再据此判断或加载约束，仅作为 Agent **可能**在最终
// 报告中回填的一个标签（可选）。前端不再让用户选择此字段。
export type TahpBugModule = 'telephony' | 'kernel-driver' | 'power-mgmt' | 'shared'

export interface BugAnalysisInput {
  rawInput: string                // 用户输入: JIRA key 或 URL
  userDescription?: string        // 用户对 Bug 的补充描述
  extraContext?: string           // 其他附加信息
}

export interface ContinueAnalysisInput {
  additionalInfo: string          // 补充上下文
}

export interface BugAnalysisTaskCtx {
  taskId: string
  parentJobId?: string            // 批量任务的父 job id
  jiraKey: string
  jiraUrl: string
  rawInput?: string               // 用户原始输入（仅作为 prompt 兜底）
  module?: TahpBugModule          // 可选 · 由 Agent 后续在报告里回填；BFF 不识别
  userDescription?: string
  extraContext?: string
  startedAt: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
  phase?: string
  progress?: number
  issue?: JiraIssue               // （已废弃 BFF JIRA fetch；保留字段防旧报告兼容）
  prevResponse?: string           // 上一轮 Agent 输出
  corrections: string[]           // 历次补充信息
  skillsUsed: string[]
  llmResponse?: string
  completedAt?: string
  error?: string
}

export interface BugAnalysisJobCtx {
  jobId: string
  type: 'single' | 'batch'
  jql?: string
  taskIds: string[]               // 关联的子任务
  startedAt: string
  status: 'running' | 'completed' | 'failed'
  total: number
  completed: number
  failed: number
}

interface TaskRuntimeControl {
  sessionId: string
  interruptRequested: boolean
}

// ─── 内存状态 ────────────────────────────────────────────────────────────────
const taskCtx = new Map<string, BugAnalysisTaskCtx>()
const jobCtx = new Map<string, BugAnalysisJobCtx>()
const taskRuntime = new Map<string, TaskRuntimeControl>()

const MAX_KEEP = 200

function pruneOldTasks() {
  if (taskCtx.size <= MAX_KEEP) return
  const ids = Array.from(taskCtx.keys())
  for (const id of ids.slice(0, taskCtx.size - MAX_KEEP)) taskCtx.delete(id)
}

// ─── ID 生成 ─────────────────────────────────────────────────────────────────

function genTaskId(prefix = 'task-bug'): string {
  return `${prefix}-${Date.now()}-${randomBytes(3).toString('hex')}`
}

// ─── 事件推送 helper ─────────────────────────────────────────────────────────

function emit(taskId: string, type: string, payload: Record<string, unknown>) {
  getTaskStream().publish({
    type,
    task_id: taskId,
    payload: { task_id: taskId, ...payload },
    ts: Date.now(),
  })
}

function settleJobIfDone(job: BugAnalysisJobCtx, aborted = false, abortReason = '') {
  if (job.completed + job.failed < job.total) return
  job.status = job.completed === 0 ? 'failed' : 'completed'
  emit(job.jobId, 'task.completed', {
    status: job.status,
    type: 'batch',
    total: job.total,
    completed: job.completed,
    failed: job.failed,
    aborted,
    message: aborted
      ? `批量 Bug 分析已终止：成功 ${job.completed} / 失败 ${job.failed}。原因：${abortReason}`
      : `批量 Bug 分析完成：成功 ${job.completed} / 失败 ${job.failed}`,
  })
}

// ─── 状态查询 (供 route 使用) ────────────────────────────────────────────────

export function getBugTask(taskId: string): BugAnalysisTaskCtx | undefined {
  return taskCtx.get(taskId)
}

export function listBugTasks(): BugAnalysisTaskCtx[] {
  return Array.from(taskCtx.values()).sort((a, b) => b.startedAt.localeCompare(a.startedAt))
}

export function getBugJob(jobId: string): BugAnalysisJobCtx | undefined {
  return jobCtx.get(jobId)
}

export function listBugJobs(): BugAnalysisJobCtx[] {
  return Array.from(jobCtx.values()).sort((a, b) => b.startedAt.localeCompare(a.startedAt))
}

// ─── 报告路径 ────────────────────────────────────────────────────────────────

function reportDir(): string {
  const d = join(tahpPaths.reportsDir, 'bug-analysis')
  if (!existsSync(d)) mkdirSync(d, { recursive: true })
  return d
}

function reportPath(taskId: string): string {
  return join(reportDir(), `${taskId}.json`)
}

export function readBugReport(taskId: string): unknown {
  const p = reportPath(taskId)
  if (!existsSync(p)) return null
  try { return JSON.parse(readFileSync(p, 'utf-8')) } catch { return null }
}

export function listBugReports(): unknown[] {
  const d = reportDir()
  if (!existsSync(d)) return []
  // 复用 sync API；批量场景这里数量不大，直接 fs readdirSync
  const fs = require('fs') as typeof import('fs')
  const files = fs.readdirSync(d).filter((f: string) => f.endsWith('.json'))
  const summaries: any[] = []
  for (const f of files) {
    try {
      const json = JSON.parse(fs.readFileSync(join(d, f), 'utf-8'))
      summaries.push({
        task_id: json.task_id,
        jira_key: json.jira_key,
        jira_url: json.jira_url,
        module: json.module,
        title: json.title,
        status: json.status,
        started_at: json.started_at,
        completed_at: json.completed_at,
        duration_ms: json.duration_ms,
        skills_used: json.skills_used || [],
        correction_of: json.correction_of,
      })
    } catch { /* skip corrupt */ }
  }
  return summaries.sort((a, b) => String(b.started_at || '').localeCompare(String(a.started_at || '')))
}

// ─── Agent Bridge 执行 ──────────────────────────────────────────────────────
//
// 说明（已移除的 BFF 启发式中间层）：
//   早期版本里 BFF 会做 inferModule / pickSkillHints / loadConstraintsSummary
//   等关键字匹配来给 Agent "提示候选"。实际效果是：
//   (a) 关键字命中率有限，往往误导多于辅助；
//   (b) Agent 拿到 JIRA 详情后会自行判断 Bug 域，BFF 的提示反而是噪声；
//   (c) 约束加载的 yaml 一锅炖（含其它 domain），意义不大。
//   因此现在直接让 Agent 用 jira-mcp / transsion-harness / BSP 分析 skill
//   一手拉数据 + 自主决策，BFF 不再做任何 Bug 域判断。

// ─── Agent Bridge 调用 ──────────────────────────────────────────────────────
//
// 通过 hermes agent-bridge 将任务发给 Claude Code Agent，监听流式输出。
// 该函数：
//   - 把 chunk.delta 经 filterBridgeToolCallMarkupDelta 过滤 tool 调用残留 markup 后，
//     以纯文本流的形式回调（onText）
//   - 解析 chunk.events 中的 tool.started / tool.completed，转换成 onTool 回调
//   - 任何 status === 'error' / 抛错都直接 throw，调用方决定是否记录任务失败
//
// 返回完整 assistant 文本（已去除 markup）。

interface AgentRunCallbacks {
  onText: (delta: string) => void
  onToolStarted: (toolName: string, args: unknown, toolCallId: unknown) => void
  onToolCompleted: (toolName: string, isError: boolean, toolCallId: unknown) => void
  onReasoning?: (text: string) => void
}

async function runAgentChat(
  sessionId: string,
  instructions: string,
  userMessage: string,
  cb: AgentRunCallbacks,
): Promise<{ fullResponse: string; runId: string }> {
  const manager = getAgentBridgeManager()
  if (!manager.running) {
    throw new Error(
      'Agent Bridge 未运行。AI Bug 分析必须依赖 Claude Code Agent（含完整 Skill / MCP 工具链），' +
      '请确认 hermes CLI 已正确安装并启动（检查服务端日志中的 [agent-bridge] starting 信息）。',
    )
  }

  let started: AgentBridgeChatStarted
  try {
    started = await sharedBridgeClient.chat(
      sessionId,
      userMessage,
      undefined, // conversation_history
      instructions,
      'default', // profile
    )
  } catch (err) {
    throw new Error(`Agent 启动失败: ${(err as Error).message}`)
  }

  const markupState: { bridgePendingToolCallMarkup?: string } = {}
  let fullResponse = ''

  let lastChunk: AgentBridgeOutput | null = null
  for await (const chunk of sharedBridgeClient.streamOutput(started.run_id, { intervalMs: 250 })) {
    lastChunk = chunk

    for (const ev of chunk.events || []) {
      const evType = ev.event as string | undefined
      if (evType === 'tool.started') {
        const toolName = (ev.tool_name as string) || 'unknown-tool'
        cb.onToolStarted(toolName, ev.args, ev.tool_call_id)
      } else if (evType === 'tool.completed') {
        const toolName = (ev.tool_name as string) || 'unknown-tool'
        cb.onToolCompleted(toolName, ev.is_error === true, ev.tool_call_id)
      } else if ((evType === 'reasoning.delta' || evType === 'thinking.delta') && cb.onReasoning) {
        cb.onReasoning(String(ev.text || ''))
      }
    }

    if (chunk.delta) {
      const cleaned = filterBridgeToolCallMarkupDelta(markupState, chunk.delta)
      if (cleaned) {
        fullResponse += cleaned
        cb.onText(cleaned)
      }
    }

    if (chunk.done) {
      if (chunk.status === 'error') {
        throw new Error(chunk.error || 'Agent 运行出错')
      }
      if (chunk.status === 'interrupted') {
        throw new Error('Agent 运行被中断')
      }
      break
    }
  }

  if (!lastChunk || !lastChunk.done) {
    throw new Error('Agent 流式输出意外终止（无终止 chunk）')
  }

  return { fullResponse, runId: started.run_id }
}

// ─── 解析 LLM 中的 <skill_use /> 标记 ────────────────────────────────────────

const SKILL_USE_RE = /<skill_use\s+([^/>]+?)\s*\/?>/g

interface SkillUseHit {
  name: string
  purpose?: string
  index: number
}

function findSkillUseHits(text: string, fromIndex = 0): SkillUseHit[] {
  const hits: SkillUseHit[] = []
  SKILL_USE_RE.lastIndex = 0
  let m: RegExpExecArray | null
  while ((m = SKILL_USE_RE.exec(text)) !== null) {
    if (m.index < fromIndex) continue
    const attrs = m[1]
    const nameMatch = attrs.match(/name\s*=\s*"([^"]+)"/) || attrs.match(/name\s*=\s*'([^']+)'/)
    if (!nameMatch) continue
    const purposeMatch = attrs.match(/purpose\s*=\s*"([^"]+)"/) || attrs.match(/purpose\s*=\s*'([^']+)'/)
    hits.push({ name: nameMatch[1], purpose: purposeMatch?.[1], index: m.index })
  }
  return hits
}

// ─── 提示词构建（Agent 模式 · 无 BFF 启发式） ───────────────────────────────
//
// BFF 不再做任何"提示候选 Skill / 加载约束摘要 / 模块识别"工作。
// Bug 域识别、Skill 选择、约束 / 上下文加载全部由 Agent 在 Step 1 拿到 JIRA
// 一手信息后自主完成。
//
// Agent 端真实可用（节选，由 Agent 自己列举 ~/.claude/skills/ 或 ~/.agents/skills/ 了解能力清单）：
//   · jira-mcp / user-jira-mcp  — 拉取 Issue / 附件 / 评论 / JQL
//   · transsion-harness          — 拉取整机日志 / 版本 / 部署
//   · com-voice-* / com-data-* / telephony-* — 通信类 BSP 日志分析
//   · near-bt-*                  — 蓝牙 / Wi-Fi / 内核驱动
//   · power-backlight-* / power-display-* / power-sensor-* — 功耗 / 亮度
//   · tones-feature-list         — 特性 / 属性查询

const AGENT_INSTRUCTIONS = `你是 TAHP（TECNO AI Harness Platform）"AI Bug 分析专家"，运行在传音 Android 底软集成部的 Claude Code Agent 环境中。

# 你的执行原则
1. **必须真正调用 Skill / MCP 工具**，不要"假装"使用 skill；用户能通过工具调用面板看到你是否真的调用了。
2. **优先用工具拉取一手数据**：JIRA 详情、日志附件、整机日志、特性清单 —— 不要凭印象。
3. **失败即停止 + 显式上报**：任何 skill / 工具调用失败时，明确指出错误原因和后续依赖，不要"猜测兜底"。
4. 中文输出。语气专业、结构清晰、可执行。

# 标准工作流（必须按此顺序执行）

## Step 1：拉取 JIRA Issue 详情（必做）
使用以下任一可用工具拉取 Issue：
- 优先：\`user-jira-mcp\` MCP（如可用）
- 备选：\`mcp__user-jira-mcp__*\` 系列工具
- 兜底：使用 transsion-harness 的 OpenGrok / JIRA 桥接（如有）

拉取目标：
- Issue Summary / Description / Status / Priority / Assignee
- 附件清单（log / dump / video）
- 评论时间线（重点关注 reporter / 测试反馈）

## Step 2：自主判断 Bug 域 + 选择对应分析 Skill（必做）
基于 Step 1 拉到的 Issue Summary / Description / Components，**自主判断**属于哪类 Bug，然后挑选对应的分析 Skill。
若不熟悉可用 Skill 清单，请先列出 \`~/.claude/skills/\` 或 \`~/.agents/skills/\` 目录了解能力。

## Step 3：日志获取（如有附件或现场需要）
- 使用 \`transsion-harness\` 拉取整机 log / kernel log / aplog / dumpsys
- 解析关键时间戳、关键字、TAG，定位异常窗口

## Step 4：根因分析（核心）
基于 JIRA 信息 + 日志关键证据 + Skill 反馈，给出根因。

## Step 5：输出标准 8 节报告
必须输出以下完整 Markdown 结构（每节 H2 标题，不要省略）：

### 1. 摘要 / TL;DR
现象 + 初步判断（≤5 行）。

### 2. 复现路径
从 JIRA / 日志中提取的复现步骤；信息不全时明确列出待补充项。

### 3. 关键日志识别
- 你实际拉取/分析过的日志文件清单（必填日志来源）
- 关键关键字 / 时间戳 / TAG / PID
- 异常窗口对应的代码栈

### 4. 根因定位（最关键）
按优先级列出 1~3 个候选根因，每个候选说明：
- 涉及模块 / 文件 / 函数（必须真实存在，不要编造）
- 触发条件 / 数据流
- 证据（直接引用日志 / 评论 / 代码）

### 5. 影响范围
机型 / 版本 / 复现概率 / 安全等级（P0/P1/P2/P3）。

### 6. 修复建议
- 代码改动方向（函数/位置/思路；**不给完整 patch**）
- 配置 / 属性 / Carrier 可调项（如有）
- TAHP 安全红线：不改 scope.excludes、不硬编码密钥、安全相关须标 Critical

### 7. 验证方案
回归 / 现场验证步骤；优先列可自动化的 smoke。

### 8. 风险与遗留问题
分析阻塞项 + 需要的额外信息。

# 输出末尾（必填）
在报告**最后一节之后**追加一段"实际使用工具清单"，逐行列出：
\`\`\`
=== TOOLS_INVOKED ===
- <工具/Skill 名>: <用途>
- ...
=== END ===
\`\`\`

# 红线
- 不要编造文件 / 函数 / 配置项名 —— 必须来自真实工具输出（JIRA / 日志 / Skill）
- 不要给完整 patch，只给修改方向
- Skill / 工具调用全程必须真实发起（前端可在 Skill 调用面板核对）
- 工具失败时直接报错并停止该步骤，不要兜底
- 不要写"如果有访问权限"之类回避用语
`

function buildAgentUserMessage(ctx: BugAnalysisTaskCtx, correction?: string): string {
  const blocks: string[] = []
  blocks.push(`# 待分析 Bug`)
  blocks.push(`- JIRA Key: **${ctx.jiraKey}**`)
  blocks.push(`- JIRA URL: ${ctx.jiraUrl}`)

  if (ctx.userDescription) {
    blocks.push('')
    blocks.push('## 用户补充描述')
    blocks.push(ctx.userDescription)
  }
  if (ctx.extraContext) {
    blocks.push('')
    blocks.push('## 附加上下文（本地已有的日志摘要等）')
    blocks.push(ctx.extraContext)
  }

  if (ctx.prevResponse) {
    blocks.push('')
    blocks.push('## 上一轮 Agent 分析结果（请基于此更新 / 修正）')
    blocks.push(ctx.prevResponse.slice(0, 4000))
  }
  if (correction) {
    blocks.push('')
    blocks.push('## 用户本轮补充信息 / 修正意见')
    blocks.push(correction)
    blocks.push('')
    blocks.push('请基于上述补充重新生成完整的 8 节分析报告。')
  } else {
    blocks.push('')
    blocks.push('请按系统提示词的标准工作流开始分析。第一步先用 JIRA Skill 拉 Issue 完整信息（含全部附件 + 评论）。')
  }

  return blocks.join('\n')
}

// ─── 单条 Bug 分析（核心执行 - Agent 模式） ─────────────────────────────────

async function runSingleBugAnalysis(
  ctx: BugAnalysisTaskCtx,
  correction?: string,        // 补充信息继续分析时传入
): Promise<void> {
  const startMs = Date.now()
  const taskId = ctx.taskId
  if (ctx.status === 'cancelled') return
  ctx.status = 'running'
  ctx.skillsUsed = ctx.skillsUsed || []
  taskCtx.set(taskId, ctx)
  pruneOldTasks()

  logBug(taskId, 'info', `开始 Bug 分析 (Agent 模式) task=${taskId} jira=${ctx.jiraKey}${correction ? ' (continue)' : ''}`)

  // 用于 destroy session 的 sessionId（即使提前 throw 也能回收）
  const agentSessionId = `tahp-bug-${taskId}`
  taskRuntime.set(taskId, { sessionId: agentSessionId, interruptRequested: false })

  try {
    // ── Phase 1: 准备提示词（无 BFF 启发式，纯组装上下文） ─────────────────
    const instructions = AGENT_INSTRUCTIONS
    const userMessage = buildAgentUserMessage(ctx, correction)
    emit(taskId, 'task.phase', {
      phase: 'PREPARING', progress: 5,
      message: '准备提交给 Agent（BFF 不做模块识别 / Skill 候选 / 约束加载）...',
    })

    // ── Phase 2: 检查 Agent Bridge 状态 ────────────────────────────────────
    emit(taskId, 'task.phase', { phase: 'CONNECTING_AGENT', progress: 15, message: '连接 Claude Code Agent...' })
    const manager = getAgentBridgeManager()
    if (!manager.running) {
      throw new Error(
        'Agent Bridge 未运行。AI Bug 分析必须由 Claude Code Agent 执行（含 Skill / MCP 工具链）。' +
        '请检查 hermes CLI 是否已安装、agent-bridge 是否启动（查看服务端日志 [agent-bridge] 行）。',
      )
    }
    emit(taskId, 'task.step', { step_id: 'connect-agent', status: 'completed', message: 'Agent Bridge 已就绪，开始下发任务...' })
    logBug(taskId, 'info', `Agent Bridge ready, session=${agentSessionId}`)

    // ── Phase 3: 把任务投递到 Agent，监听 tool.* / 文本 delta ──────────────
    emit(taskId, 'task.phase', { phase: 'ANALYZING', progress: 25, message: 'Agent 正在分析（可在右侧实时观察 Skill / 工具调用）...' })

    let lastSkillHitIdx = 0
    let toolCallCount = 0
    let textDeltaCount = 0

    const { fullResponse } = await runAgentChat(agentSessionId, instructions, userMessage, {
      onText: (delta) => {
        textDeltaCount += 1
        emit(taskId, 'task.message', { level: 'stream', text: delta })

        // Agent 输出里也可能出现 <skill_use /> 标签（兼容旧产物格式）
        const fullSoFar = (ctx.llmResponse || '') + delta
        ctx.llmResponse = fullSoFar
        const hits = findSkillUseHits(fullSoFar, lastSkillHitIdx)
        for (const h of hits) {
          if (!ctx.skillsUsed.includes(h.name)) {
            ctx.skillsUsed.push(h.name)
            emit(taskId, 'task.skill_use', {
              skill_id: h.name,
              source: 'text_marker',
              purpose: h.purpose || '',
              message: `Skill 标记：${h.name}${h.purpose ? ' — ' + h.purpose : ''}`,
            })
            logBug(taskId, 'info', `skill_use (marker): ${h.name}`)
          }
          lastSkillHitIdx = Math.max(lastSkillHitIdx, h.index + 1)
        }
      },
      onToolStarted: (toolName, args, toolCallId) => {
        toolCallCount += 1
        if (!ctx.skillsUsed.includes(toolName)) ctx.skillsUsed.push(toolName)
        const argPreview = summarizeArgs(args)
        emit(taskId, 'task.skill_use', {
          skill_id: toolName,
          source: 'tool_call',
          tool_call_id: toolCallId,
          args: argPreview,
          purpose: `Agent 真实调用工具 ${toolName}`,
          message: `🛠 Agent 调用：${toolName}${argPreview ? ` ${argPreview}` : ''}`,
        })
        logBug(taskId, 'info', `tool.started: ${toolName} ${argPreview}`)
      },
      onToolCompleted: (toolName, isError, toolCallId) => {
        emit(taskId, 'task.tool_completed', {
          skill_id: toolName,
          tool_call_id: toolCallId,
          error: isError,
          message: isError ? `✗ 工具失败：${toolName}` : `✓ 工具完成：${toolName}`,
        })
        logBug(taskId, isError ? 'warn' : 'info', `tool.completed: ${toolName} ${isError ? '(error)' : ''}`)
      },
      onReasoning: (text) => {
        if (text) emit(taskId, 'task.message', { level: 'reasoning', text })
      },
    })

    // 把最终（filter 后）完整响应回填，覆盖增量过程中暂存的中间值
    ctx.llmResponse = fullResponse

    emit(taskId, 'task.step', {
      step_id: 'analyzing', status: 'completed',
      message: `Agent 分析完成：${fullResponse.length} 字, 工具调用 ${toolCallCount} 次, 文本分片 ${textDeltaCount}`,
    })
    logBug(taskId, 'info', `Agent run complete (${fullResponse.length} chars, tools=${toolCallCount}, skills_recorded=${ctx.skillsUsed.join(',') || 'none'})`)

    // ── Phase 4: GENERATING_REPORT ───────────────────────────────────────
    emit(taskId, 'task.phase', { phase: 'GENERATING_REPORT', progress: 92, message: '生成报告并落盘...' })
    ctx.llmResponse = fullResponse
    ctx.prevResponse = fullResponse
    if (correction) ctx.corrections.push(correction)

    const completedAt = new Date().toISOString()
    const durationMs = Date.now() - startMs
    ctx.status = 'completed'
    ctx.completedAt = completedAt

    const issue = ctx.issue || null
    const report = {
      task_id: taskId,
      jira_key: ctx.jiraKey,
      jira_url: ctx.jiraUrl,
      module: ctx.module,
      title: issue?.summary || ctx.rawInput || ctx.jiraKey,
      status: 'completed',
      execution_mode: 'agent', // 明确标识：本任务由 Claude Code Agent 执行
      agent_session_id: agentSessionId,
      started_at: ctx.startedAt,
      completed_at: completedAt,
      duration_ms: durationMs,
      user_description: ctx.userDescription,
      extra_context: ctx.extraContext,
      corrections: ctx.corrections,
      correction_of: undefined,
      skills_used: ctx.skillsUsed,
      tool_call_count: toolCallCount,
      llm_response: fullResponse,
      jira: issue ? {
        key: issue.key,
        url: issue.url,
        summary: issue.summary,
        status: issue.status,
        priority: issue.priority,
        assignee: issue.assignee,
        reporter: issue.reporter,
        components: issue.components,
        labels: issue.labels,
        attachments: issue.attachments,
        description: issue.description?.slice(0, 5000),
        commentCount: issue.comments.length,
      } : { key: ctx.jiraKey, url: ctx.jiraUrl, note: '未在 BFF 端预拉取，由 Agent Skill 拉取' },
    }
    try {
      writeFileSync(reportPath(taskId), JSON.stringify(report, null, 2), 'utf-8')
      emit(taskId, 'task.step', { step_id: 'generate-report', status: 'completed', message: '报告已落盘' })
      logBug(taskId, 'info', `report written: ${reportPath(taskId)}`)
    } catch (e) {
      logBug(taskId, 'error', `report write failed: ${(e as Error).message}`)
    }

    emit(taskId, 'task.completed', {
      status: 'completed',
      jira_key: ctx.jiraKey,
      module: ctx.module,
      duration_ms: durationMs,
      skills_used: ctx.skillsUsed,
      response_length: fullResponse.length,
      message: `Bug 分析完成（${ctx.jiraKey}），使用 Skill: ${ctx.skillsUsed.join(', ') || '无'}`,
    })

    // ── 更新父 job 状态 ───────────────────────────────────────────────────
    if (ctx.parentJobId) {
      const job = jobCtx.get(ctx.parentJobId)
      if (job) {
        job.completed += 1
        if (job.completed + job.failed >= job.total) {
          job.status = job.failed === 0 ? 'completed' : (job.completed === 0 ? 'failed' : 'completed')
          emit(job.jobId, 'task.completed', {
            status: job.status,
            type: 'batch',
            total: job.total,
            completed: job.completed,
            failed: job.failed,
            message: `批量 Bug 分析完成：成功 ${job.completed} / 失败 ${job.failed}`,
          })
        } else {
          emit(job.jobId, 'task.phase', {
            phase: 'BATCH_RUNNING',
            progress: Math.round(((job.completed + job.failed) / job.total) * 100),
            message: `批量进度 ${job.completed + job.failed} / ${job.total}`,
          })
        }
      }
    }

  } catch (err) {
    const control = taskRuntime.get(taskId)
    const interruptedByUser = control?.interruptRequested === true
    const msg = interruptedByUser ? '任务已被用户中断' : (err as Error).message
    logger.warn({ taskId, err: msg }, '[bug-analysis] failed')
    logBug(taskId, interruptedByUser ? 'warn' : 'error', `task failed: ${msg}`)
    ctx.status = interruptedByUser ? 'cancelled' : 'failed'
    ctx.error = msg
    ctx.completedAt = new Date().toISOString()
    if (interruptedByUser) {
      emit(taskId, 'task.cancelled', { error: msg, message: msg })
    } else {
      emit(taskId, 'task.failed', { error: msg, message: `分析失败: ${msg}` })
    }

    // 写入失败报告
    try {
      const report = {
        task_id: taskId,
        jira_key: ctx.jiraKey,
        jira_url: ctx.jiraUrl,
        module: ctx.module,
        status: 'failed',
        error: msg,
        started_at: ctx.startedAt,
        completed_at: ctx.completedAt,
        user_description: ctx.userDescription,
        extra_context: ctx.extraContext,
      }
      writeFileSync(reportPath(taskId), JSON.stringify(report, null, 2), 'utf-8')
    } catch { /* swallow */ }

    if (ctx.parentJobId) {
      const job = jobCtx.get(ctx.parentJobId)
      if (job) {
        job.failed += 1
        if (job.completed + job.failed >= job.total) {
          settleJobIfDone(job)
        } else {
          emit(job.jobId, 'task.phase', {
            phase: 'BATCH_RUNNING',
            progress: Math.round(((job.completed + job.failed) / job.total) * 100),
            message: `批量进度 ${job.completed + job.failed} / ${job.total}`,
          })
        }
      }
    }
  } finally {
    // 释放 Agent Pool 中对应的 session（失败/成功都做，幂等）
    sharedBridgeClient.destroy(agentSessionId).catch((e) => {
      logBug(taskId, 'warn', `destroy agent session failed: ${(e as Error).message}`)
    })
    taskRuntime.delete(taskId)
    await appendBugLog(taskId, 'info', '── task end ──')
  }
}

// ─── 工具调用参数摘要 (用于 task.skill_use 消息展示) ────────────────────────

function summarizeArgs(args: unknown): string {
  if (!args || typeof args !== 'object') return ''
  const obj = args as Record<string, unknown>
  const keys = Object.keys(obj)
  if (keys.length === 0) return ''
  // 抓 1~2 个最关键字段做预览（command/path/url/query/...）
  const prio = ['command', 'cmd', 'shell', 'tool', 'path', 'file', 'file_path', 'url', 'query', 'jql', 'key', 'issue_key']
  const picked: string[] = []
  for (const k of prio) {
    if (k in obj) {
      const v = obj[k]
      if (typeof v === 'string') picked.push(`${k}=${truncateStr(v, 60)}`)
      else if (v != null) picked.push(`${k}=${truncateStr(JSON.stringify(v), 60)}`)
      if (picked.length >= 2) break
    }
  }
  if (picked.length === 0) {
    const first = keys[0]
    const v = obj[first]
    if (typeof v === 'string') picked.push(`${first}=${truncateStr(v, 60)}`)
    else picked.push(`${first}=${truncateStr(JSON.stringify(v), 60)}`)
  }
  return `(${picked.join(', ')})`
}

function truncateStr(s: string, max: number): string {
  if (s.length <= max) return s
  return s.slice(0, max - 1) + '…'
}

// ─── 公开入口：启动单条 Bug 分析 ─────────────────────────────────────────────

export interface StartTaskResult {
  ok: boolean
  taskId?: string
  jiraKey?: string
  error?: string
}

export function startSingleBugAnalysis(input: BugAnalysisInput): StartTaskResult {
  const key = parseIssueKey(input.rawInput)
  if (!key) return { ok: false, error: `无法从输入解析 JIRA Key: ${input.rawInput}` }

  const taskId = genTaskId()
  const jiraBase = (process.env.TAHP_JIRA_BASE_URL || 'http://jira.transsion.com').replace(/\/+$/, '')
  const ctx: BugAnalysisTaskCtx = {
    taskId,
    jiraKey: key,
    jiraUrl: `${jiraBase}/browse/${key}`,
    rawInput: input.rawInput,
    userDescription: input.userDescription,
    extraContext: input.extraContext,
    startedAt: new Date().toISOString(),
    status: 'running',
    corrections: [],
    skillsUsed: [],
  }
  taskCtx.set(taskId, ctx)

  emit(taskId, 'task.started', {
    type: 'single',
    jira_key: key,
    jira_url: ctx.jiraUrl,
    message: `AI Bug 分析任务已启动: ${key}`,
  })
  logBug(taskId, 'info', `task.started single ${key}`)

  setImmediate(() => {
    runSingleBugAnalysis(ctx).catch(err => {
      logger.error({ err: (err as Error).message, taskId }, '[bug-analysis] unhandled')
    })
  })

  return { ok: true, taskId, jiraKey: key }
}

// ─── 公开入口：补充信息继续分析 ─────────────────────────────────────────────

export function continueBugAnalysis(prevTaskId: string, input: ContinueAnalysisInput): StartTaskResult {
  const prev = taskCtx.get(prevTaskId)
  if (!prev) {
    // 尝试从报告恢复（场景：服务重启）
    const report = readBugReport(prevTaskId) as any
    if (!report) return { ok: false, error: `找不到原任务 ${prevTaskId}` }
    const newTaskId = genTaskId()
    const ctx: BugAnalysisTaskCtx = {
      taskId: newTaskId,
      jiraKey: report.jira_key,
      jiraUrl: report.jira_url,
      module: report.module as TahpBugModule | undefined,
      userDescription: report.user_description,
      extraContext: report.extra_context,
      startedAt: new Date().toISOString(),
      status: 'running',
      corrections: Array.isArray(report.corrections) ? [...report.corrections] : [],
      skillsUsed: [],
      prevResponse: report.llm_response,
    }
    taskCtx.set(newTaskId, ctx)
    emit(newTaskId, 'task.started', {
      type: 'continue',
      from_task_id: prevTaskId,
      jira_key: ctx.jiraKey,
      jira_url: ctx.jiraUrl,
      message: `补充信息继续分析: ${ctx.jiraKey}（基于报告恢复）`,
    })
    setImmediate(() => {
      runSingleBugAnalysis(ctx, input.additionalInfo).catch(err => {
        logger.error({ err: (err as Error).message, newTaskId }, '[bug-analysis] continue unhandled')
      })
    })
    return { ok: true, taskId: newTaskId, jiraKey: ctx.jiraKey }
  }

  const newTaskId = genTaskId()
  const ctx: BugAnalysisTaskCtx = {
    taskId: newTaskId,
    jiraKey: prev.jiraKey,
    jiraUrl: prev.jiraUrl,
    module: prev.module,
    userDescription: prev.userDescription,
    extraContext: prev.extraContext,
    startedAt: new Date().toISOString(),
    status: 'running',
    corrections: [...prev.corrections],
    skillsUsed: [],
    issue: prev.issue,
    prevResponse: prev.llmResponse || prev.prevResponse,
  }
  taskCtx.set(newTaskId, ctx)
  emit(newTaskId, 'task.started', {
    type: 'continue',
    from_task_id: prevTaskId,
    jira_key: ctx.jiraKey,
    jira_url: ctx.jiraUrl,
    message: `补充信息继续分析: ${ctx.jiraKey}`,
  })
  logBug(newTaskId, 'info', `task.started continue from=${prevTaskId} jira=${ctx.jiraKey}`)

  setImmediate(() => {
    runSingleBugAnalysis(ctx, input.additionalInfo).catch(err => {
      logger.error({ err: (err as Error).message, newTaskId }, '[bug-analysis] continue unhandled')
    })
  })

  return { ok: true, taskId: newTaskId, jiraKey: ctx.jiraKey }
}

// ─── 公开入口：JQL 批量分析 ──────────────────────────────────────────────────

export interface StartBatchResult {
  ok: boolean
  jobId?: string
  total?: number
  tasks?: Array<{ task_id: string; jira_key: string }>
  error?: string
}

const MAX_BATCH_SIZE = 20

export async function startBatchBugAnalysis(jql: string, extraContext?: string, jiraCfg?: JiraConfig): Promise<StartBatchResult> {
  if (!jql?.trim()) return { ok: false, error: '空 JQL' }

  const jobId = genTaskId('task-bugjob')
  const search = await searchJQL(jql, jiraCfg, MAX_BATCH_SIZE)
  if (!search.ok || !search.data) {
    return { ok: false, error: search.error || 'JQL 查询失败' }
  }
  const candidates = search.data.issues
  if (!candidates.length) {
    return { ok: false, error: 'JQL 未匹配到任何 Issue' }
  }

  const job: BugAnalysisJobCtx = {
    jobId,
    type: 'batch',
    jql,
    taskIds: [],
    startedAt: new Date().toISOString(),
    status: 'running',
    total: candidates.length,
    completed: 0,
    failed: 0,
  }
  jobCtx.set(jobId, job)

  const tasks: Array<{ task_id: string; jira_key: string }> = []
  for (const issue of candidates) {
    const tid = genTaskId()
    const ctx: BugAnalysisTaskCtx = {
      taskId: tid,
      parentJobId: jobId,
      jiraKey: issue.key,
      jiraUrl: issue.url,
      startedAt: new Date().toISOString(),
      status: 'pending',
      corrections: [],
      skillsUsed: [],
      extraContext,
    }
    taskCtx.set(tid, ctx)
    job.taskIds.push(tid)
    tasks.push({ task_id: tid, jira_key: issue.key })
  }

  emit(jobId, 'task.started', {
    type: 'batch',
    jql,
    total: candidates.length,
    truncated: search.data.truncated,
    tasks,
    message: `批量 Bug 分析启动：共 ${candidates.length} 单${search.data.truncated ? '（已截断至上限）' : ''}`,
  })
  logBug(jobId, 'info', `batch.started jql=${jql.slice(0, 200)} total=${candidates.length}`)

  // 串行执行（避免 Agent 并发过高，且方便用户在 UI 上跟随观察）。
  // 任一子任务 Agent 失败 → **终止后续任务**（按用户需求，不再继续跑剩下的）。
  // 剩余未跑的任务会被标记为 cancelled，并在事件流里显示原因。
  setImmediate(async () => {
    let aborted = false
    let abortReason = ''
    for (const tid of job.taskIds) {
      const ctx = taskCtx.get(tid)
      if (!ctx) continue
      if (ctx.status === 'cancelled') continue

      if (aborted) {
        ctx.status = 'failed'
        ctx.error = `批量已终止：${abortReason}`
        ctx.completedAt = new Date().toISOString()
        emit(tid, 'task.failed', {
          parent_job_id: jobId,
          error: ctx.error,
          message: `子任务取消（前序任务失败已终止批量）`,
        })
        logBug(tid, 'warn', `child task cancelled (batch aborted): ${abortReason}`)
        job.failed += 1
        continue
      }

      emit(tid, 'task.started', {
        type: 'single',
        parent_job_id: jobId,
        jira_key: ctx.jiraKey,
        jira_url: ctx.jiraUrl,
        message: `子任务启动: ${ctx.jiraKey}`,
      })
      logBug(tid, 'info', `child task.started parent=${jobId}`)

      try {
        await runSingleBugAnalysis(ctx)
        if (ctx.status === 'failed') {
          aborted = true
          abortReason = ctx.error || '子任务执行失败'
          logger.warn({ jobId, tid, reason: abortReason }, '[bug-analysis] batch aborted due to child failure')
          emit(jobId, 'task.message', {
            level: 'warn',
            text: `子任务 ${ctx.jiraKey} 失败，终止批量后续任务：${abortReason}`,
          })
          logBug(jobId, 'warn', `batch aborted by child ${tid}: ${abortReason}`)
        }
        const latest = taskCtx.get(tid)
        if (latest?.status === 'cancelled') {
          logBug(jobId, 'warn', `child task cancelled by user: ${tid}`)
        }
      } catch (err) {
        aborted = true
        abortReason = (err as Error).message
        logger.warn({ err: abortReason, tid }, '[bug-analysis] batch child threw')
      }
    }

    // 最终态修正（runSingleBugAnalysis 内部会维护正常完成路径的 job.status，
    // 但若中途 cancel 了剩余任务，状态可能还未到 terminal state）
    if (job.status === 'running') {
      const allDone = job.completed + job.failed >= job.total
      if (allDone) {
        settleJobIfDone(job, aborted, abortReason)
      }
    }
  })

  return { ok: true, jobId, total: candidates.length, tasks }
}

// ─── Helper: 从内存或 JIRA fetch 出一份完整的 issue 预览（供前端单独预览） ───

export async function previewSingleIssue(
  rawInput: string,
  jiraCfg?: JiraConfig,
): Promise<{ ok: boolean; key?: string; issue?: JiraIssue; error?: string }> {
  const key = parseIssueKey(rawInput)
  if (!key) return { ok: false, error: `无法解析 JIRA Key: ${rawInput}` }
  const r = await fetchIssue(key, jiraCfg)
  if (!r.ok || !r.data) return { ok: false, key, error: r.error || 'JIRA fetch 失败' }
  return { ok: true, key, issue: r.data }
}

// 暴露用于测试 / 路由直接使用
export { genTaskId as _genTaskId }
// 暴露 jira summary helper for batch preview
export { searchJQL as _previewJQL, fetchIssue as _previewIssue }

export async function cancelBugTask(taskId: string): Promise<{ ok: boolean; action?: 'cancelled_pending' | 'interrupted_running'; error?: string }> {
  const ctx = taskCtx.get(taskId)
  if (!ctx) return { ok: false, error: `找不到任务: ${taskId}` }
  if (ctx.status === 'completed' || ctx.status === 'failed' || ctx.status === 'cancelled') {
    return { ok: false, error: `任务已结束，当前状态: ${ctx.status}` }
  }

  if (ctx.status === 'pending') {
    ctx.status = 'cancelled'
    ctx.error = '任务已取消（等待中）'
    ctx.completedAt = new Date().toISOString()
    emit(taskId, 'task.cancelled', { error: ctx.error, message: ctx.error })
    logBug(taskId, 'warn', 'task cancelled while pending')
    if (ctx.parentJobId) {
      const job = jobCtx.get(ctx.parentJobId)
      if (job) {
        job.failed += 1
        settleJobIfDone(job)
      }
    }
    return { ok: true, action: 'cancelled_pending' }
  }

  const control = taskRuntime.get(taskId) || { sessionId: `tahp-bug-${taskId}`, interruptRequested: false }
  control.interruptRequested = true
  taskRuntime.set(taskId, control)
  emit(taskId, 'task.message', { level: 'warn', text: '已请求强行中断任务，等待 Agent 停止...' })
  logBug(taskId, 'warn', `task interrupt requested: ${control.sessionId}`)

  // 后台执行中断，避免前端请求阻塞导致“点击无反应”
  setImmediate(() => {
    sharedBridgeClient.interrupt(control.sessionId, '用户手动中断任务').catch((err) => {
      logBug(taskId, 'warn', `task interrupt rpc failed: ${(err as Error).message}`)
    })
  })
  return { ok: true, action: 'interrupted_running' }
}

export type { JiraIssue, JiraIssueSummary }
