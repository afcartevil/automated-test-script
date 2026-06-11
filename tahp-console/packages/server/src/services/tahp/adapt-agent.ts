/**
 * TAHP — AI 适配调试 · Agent 自动适配（桥接 Agent）
 *
 * 将关联 Skill + 表单参数投递到 Hermes Agent Bridge，经 TaskStream 推送进度。
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
  buildFullTahpSystemContext,
  getTahpSkillsRoot,
  tahpSkillMdPath,
} from './context-injector'
import { saveAgentPromptLog } from './prompt-log'
import { resolveFormFieldLabels } from './adapt-layout/service'
import {
  extractAdaptAgentFileChanges,
  extractAdaptAgentSkillRefs,
} from './adapt-agent-report'

const sharedBridgeClient = new AgentBridgeClient({ timeoutMs: 30 * 60_000 })

/** 适配完成后主 Agent 自检用的编码规范审核 Skill（方案四：Prompt + Skill） */
export const ADAPT_AUDIT_SKILL_ID = 'transsion-coding-standards-review'

const AUDIT_SECTION_MARKERS = [
  '## Skill 遵从性自检',
  '# 编码规范审核报告',
  '## 编码规范审核报告',
]

export interface AdaptAgentFieldMeta {
  name: string
  label: string
  required?: boolean
}

export interface AdaptAgentRunInput {
  domainId: string
  domainLabel: string
  module: string
  relatedSkills: string[]
  formData: Record<string, string>
  formFields?: AdaptAgentFieldMeta[]
  userNotes?: string
}

export interface AdaptAgentTaskCtx {
  taskId: string
  domainId: string
  domainLabel: string
  module: string
  relatedSkills: string[]
  formData: Record<string, string>
  formFields?: AdaptAgentFieldMeta[]
  userNotes?: string
  startedAt: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  phase?: string
  progress?: number
  skillsUsed: string[]
  toolsUsed: Array<{ name: string; status: 'running' | 'done' | 'error'; preview?: string }>
  fileChanges: Array<{ path: string; action: string; tool: string; at: string }>
  planNotes: string[]
  llmResponse?: string
  /** 从完整输出中切出的自检/审核章节（报告末尾） */
  auditReport?: string
  auditSkillId?: string
  promptLogDir?: string
  completedAt?: string
  error?: string
}

const taskCtx = new Map<string, AdaptAgentTaskCtx>()

function genTaskId(): string {
  return `task-adapt-agent-${Date.now()}-${randomBytes(3).toString('hex')}`
}

function emit(taskId: string, type: string, payload: Record<string, unknown>) {
  getTaskStream().publish({
    type,
    task_id: taskId,
    payload: { task_id: taskId, ...payload },
    ts: Date.now(),
  })
}

function truncateStr(s: string, max: number): string {
  return s.length <= max ? s : `${s.slice(0, max)}…`
}

function summarizeArgs(args: unknown): string {
  if (!args || typeof args !== 'object') return ''
  const obj = args as Record<string, unknown>
  const keys = Object.keys(obj)
  if (keys.length === 0) return ''
  const prio = ['command', 'cmd', 'path', 'file', 'file_path', 'old_string', 'new_string', 'skill', 'query']
  const picked: string[] = []
  for (const k of prio) {
    if (k in obj) {
      const v = obj[k]
      if (typeof v === 'string') picked.push(`${k}=${truncateStr(v, 80)}`)
      else if (v != null) picked.push(`${k}=${truncateStr(JSON.stringify(v), 80)}`)
      if (picked.length >= 2) break
    }
  }
  if (picked.length === 0 && keys[0]) {
    const v = obj[keys[0]]
    picked.push(`${keys[0]}=${truncateStr(typeof v === 'string' ? v : JSON.stringify(v), 80)}`)
  }
  return picked.length ? `(${picked.join(', ')})` : ''
}

const FILE_WRITE_TOOLS = new Set([
  'write', 'write_file', 'edit', 'str_replace', 'str_replace_based_edit_tool', 'apply_patch',
  'Write', 'Edit', 'MultiEdit', 'patch',
])

const READ_ONLY_TOOLS = new Set(['read_file', 'read', 'Read'])

function extractFilePathFromArgs(args: unknown): string | undefined {
  if (!args || typeof args !== 'object') return undefined
  const obj = args as Record<string, unknown>
  for (const k of ['path', 'file_path', 'file', 'target_file', 'notebook_path']) {
    const v = obj[k]
    if (typeof v === 'string' && v.trim()) return v.trim()
  }
  return undefined
}

/** 从 Agent 完整输出中提取末尾的自检/审核报告（含 Skill 遵从性 + 编码规范两段） */
export function extractAdaptAuditReport(fullResponse: string): string | undefined {
  const skillIdx = fullResponse.lastIndexOf('## Skill 遵从性自检')
  if (skillIdx >= 0) return fullResponse.slice(skillIdx).trim()

  let codingIdx = -1
  for (const marker of AUDIT_SECTION_MARKERS) {
    if (marker === '## Skill 遵从性自检') continue
    const idx = fullResponse.lastIndexOf(marker)
    if (idx > codingIdx) codingIdx = idx
  }
  if (codingIdx < 0) return undefined
  return fullResponse.slice(codingIdx).trim()
}

function buildWorkflowHint(domainId: string, primarySkill: string): string {
  if (domainId === 'comm-framework') {
    return [
      '# 主控 Skill 工作流（通信框架测试）',
      '- 校验 `prj_path` 是否有效',
      '- 在 `prj_path` 下创建测试文件',
      '- 按步骤多次写入（步骤、时间、地点、天气）',
      '- 输出最终文件路径与写入结果',
    ].join('\n')
  }
  if (domainId === 'modem') {
    return [
      '# 主控 Skill 工作流（MODEM P1 参考）',
      '- 校验 4 个全局路径 + BOM 名称 + 变更后 BOM + RF 目标仓',
      '- 调度 RF 移植子技能 → 获取上下文变量 X、Y',
      '- 调度宏控移植子技能 → 汇总报告',
    ].join('\n')
  }
  return [
    `# 主控 Skill 工作流（${primarySkill}）`,
    `- 先 Read 主控 Skill：\`${primarySkill}\` 全文，严格按其中 SOP 执行`,
    '- 用户表单参数已提供则核对后使用，勿重复询问已有项',
    '- 按主控 Skill 调度下列关联 Skill（顺序执行，必要时 Read 全文）',
    '- 输出结构化总结与文件修改清单',
  ].join('\n')
}

function buildAdaptAgentInstructions(input: AdaptAgentRunInput, userMessage: string): string {
  const primarySkill = input.relatedSkills[0]
  const skillsDir = getTahpSkillsRoot()
  const skillPaths = input.relatedSkills
    .map((id, idx) => `- ${idx === 0 ? '**主控**' : '关联'} **${id}**: \`${tahpSkillMdPath(id)}\``)
    .join('\n')
  const auditSkillPath = tahpSkillMdPath(ADAPT_AUDIT_SKILL_ID)
  const workflowHint = buildWorkflowHint(input.domainId, primarySkill)

  const base = `你是 TAHP「AI 适配调试 · Agent 自动适配」专家，负责在传音 Android 底软集成部完成 **${input.domainLabel}** 的适配任务。

# 必须遵守
1. **先 Read 主控 Skill 全文**：\`${tahpSkillMdPath(primarySkill)}\`，再按其中 SOP 逐步执行，不得跳过「收集参数」类步骤（用户已在表单中提供则核对后使用）。
2. **关联 Skill（按流程调度）**：
${skillPaths}
3. **必须真实调用工具**；每完成一个主要阶段，用简短 Markdown 输出「任务规划 / 当前步骤 / 下一步」。
4. 涉及代码或配置修改时，使用 Write/Edit 等工具；**禁止编造路径**。
5. 适配工作全部完成后，输出结构化总结，必须包含以下章节：
   - ## 任务规划回顾
   - ## 已使用的 Skill
   - ## 文件修改清单（路径 + 修改说明；若无修改写「无」）
   - ## 升级/适配结果摘要
   - ## 风险与待用户确认项
6. **最后一步（不得跳过）— 自检审核**：Read 审核 Skill 全文 \`${auditSkillPath}\`（\`${ADAPT_AUDIT_SKILL_ID}\`），在**全部适配总结之后**追加，且**必须严格按下列顺序与格式**：
   - **先输出固定概览表** \`## 审核结果概览\`（系统据此解析，禁止省略或改列名）：
     \`\`\`
     ## 审核结果概览

     | 检查环节 | 结果 | 说明 |
     |----------|------|------|
     | Skill 遵从性自检 | PASS 或 FAIL 或 WARN | 一行精简说明 |
     | 编码规范审核报告 | PASS 或 FAIL 或 WARN | 一行精简说明 |
     | AOSP 流程风险评估 | PASS 或 FAIL 或 WARN 或 N/A | 一行精简说明 |
     \`\`\`
   - 再输出 \`## Skill 遵从性自检\` 详情（须含 \`**结论**:\` 行，写 PASS/FAIL 及一句总结）
   - 再输出 \`# 编码规范审核报告\`（含 \`## 概览\` 与 \`**总体结论**:\`，严格按 \`${ADAPT_AUDIT_SKILL_ID}\` 模板）
7. 最终回复顺序：**适配总结 → 审核结果概览表 → Skill 遵从性自检 → 编码规范审核报告**。
8. \`## 文件修改清单\` 中每条路径必须用反引号包裹绝对路径（如 \`D:\\\\path\\\\file.txt\`），便于系统收录。

${workflowHint}

# 审核 Skill（适配完成后必读）
- **${ADAPT_AUDIT_SKILL_ID}**: \`${auditSkillPath}\`

# 工程 Skill 根目录
\`${skillsDir}\`
`

  const tahpCtx = buildFullTahpSystemContext(userMessage, {
    scenario: 'adapt_debug',
    preferredSkillIds: [...input.relatedSkills, ADAPT_AUDIT_SKILL_ID],
  })
  return tahpCtx ? `${base}\n\n${tahpCtx}` : base
}

function buildAdaptAgentUserMessage(input: AdaptAgentRunInput): string {
  const lines: string[] = [
    `# ${input.domainLabel} — Agent 自动适配任务`,
    '',
    '## 适配域信息',
    `- 域 ID: ${input.domainId}`,
    `- TAHP 模块: ${input.module}`,
    '',
    '## 用户已填写的表单参数（必须使用，勿重复询问已有项）',
  ]
  const rows = resolveFormFieldLabels(input.formData, input.formFields)
  for (const row of rows) {
    lines.push(`- **${row.label}** (\`${row.name}\`): ${row.value}`)
  }
  lines.push('')
  lines.push(`## 关联 Skills（须按主控 Skill 调度）`)
  lines.push(`**主控 Skill**: ${input.relatedSkills[0]}`)
  if (input.relatedSkills.length > 1) {
    lines.push(`**协同 Skill**: ${input.relatedSkills.slice(1).join(', ')}`)
  }
  lines.push(`**关联 Skills**: ${input.relatedSkills.join(', ')}`)
  if (input.userNotes?.trim()) {
    lines.push('')
    lines.push('## 用户补充说明')
    lines.push(input.userNotes.trim())
  }
  lines.push('')
  lines.push('请立即开始：Read 主控 Skill，输出任务规划，然后按 SOP 执行适配。')
  lines.push(`全部适配完成后，必须 Read \`${ADAPT_AUDIT_SKILL_ID}\`，在报告末尾先输出「## 审核结果概览」三行 PASS/FAIL 表，再写详细审核章节。`)
  return lines.join('\n')
}

/** 构建将发往 Agent Bridge 的最终提示词（不启动任务） */
export function buildAdaptAgentPrompts(input: AdaptAgentRunInput): {
  systemPrompt: string
  userPrompt: string
} {
  const userPrompt = buildAdaptAgentUserMessage(input)
  const systemPrompt = buildAdaptAgentInstructions(input, userPrompt)
  return { systemPrompt, userPrompt }
}

async function runAgentChat(
  sessionId: string,
  instructions: string,
  userMessage: string,
  cb: {
    onText: (delta: string) => void
    onToolStarted: (toolName: string, args: unknown, toolCallId: unknown) => void
    onToolCompleted: (toolName: string, isError: boolean, toolCallId: unknown) => void
    onReasoning?: (text: string) => void
  },
): Promise<{ fullResponse: string }> {
  const manager = getAgentBridgeManager()
  if (!manager.running) {
    throw new Error(
      'Agent Bridge 未运行。请确认 hermes CLI 已安装且 agent-bridge 已启动（服务端日志 [agent-bridge]）。',
    )
  }

  const started: AgentBridgeChatStarted = await sharedBridgeClient.chat(
    sessionId,
    userMessage,
    undefined,
    instructions,
    'default',
  )

  const markupState: { bridgePendingToolCallMarkup?: string } = {}
  let fullResponse = ''
  let lastChunk: AgentBridgeOutput | null = null

  for await (const chunk of sharedBridgeClient.streamOutput(started.run_id, { intervalMs: 250 })) {
    lastChunk = chunk
    for (const ev of chunk.events || []) {
      const evType = ev.event as string | undefined
      if (evType === 'tool.started') {
        cb.onToolStarted((ev.tool_name as string) || 'unknown-tool', ev.args, ev.tool_call_id)
      } else if (evType === 'tool.completed') {
        cb.onToolCompleted((ev.tool_name as string) || 'unknown-tool', ev.is_error === true, ev.tool_call_id)
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
      if (chunk.status === 'error') throw new Error(chunk.error || 'Agent 运行出错')
      if (chunk.status === 'interrupted') throw new Error('Agent 运行被中断')
      break
    }
  }

  if (!lastChunk?.done) throw new Error('Agent 流式输出意外终止')
  return { fullResponse }
}

function reportDir(): string {
  const d = join(tahpPaths.reportsDir, 'adapt-agent')
  if (!existsSync(d)) mkdirSync(d, { recursive: true })
  return d
}

export function getAdaptAgentTask(taskId: string): AdaptAgentTaskCtx | undefined {
  return taskCtx.get(taskId)
}

export function startAdaptAgentRun(input: AdaptAgentRunInput): { ok: true; taskId: string } | { ok: false; error: string } {
  if (!input.relatedSkills?.length) {
    return { ok: false, error: '缺少关联 Skill' }
  }
  const requiredKeys = (input.formFields || []).filter(f => f.required).map(f => f.name)
  for (const k of requiredKeys) {
    if (!String(input.formData[k] || '').trim()) {
      const label = input.formFields?.find(f => f.name === k)?.label || k
      return { ok: false, error: `缺少必填参数: ${label}` }
    }
  }

  const taskId = genTaskId()
  const ctx: AdaptAgentTaskCtx = {
    taskId,
    domainId: input.domainId,
    domainLabel: input.domainLabel,
    module: input.module,
    relatedSkills: [...input.relatedSkills],
    formData: { ...input.formData },
    formFields: input.formFields ? [...input.formFields] : undefined,
    userNotes: input.userNotes,
    startedAt: new Date().toISOString(),
    status: 'running',
    skillsUsed: [],
    toolsUsed: [],
    fileChanges: [],
    planNotes: [],
  }
  taskCtx.set(taskId, ctx)

  emit(taskId, 'task.started', {
    mode: 'agent',
    domain_id: input.domainId,
    domain_label: input.domainLabel,
    related_skills: input.relatedSkills,
    message: `${input.domainLabel} Agent 自动适配已启动`,
  })

  setImmediate(() => {
    runAdaptAgentTask(taskId).catch(err => {
      logger.error({ err, taskId }, '[adapt-agent] unhandled')
    })
  })

  return { ok: true, taskId }
}

async function runAdaptAgentTask(taskId: string): Promise<void> {
  const ctx = taskCtx.get(taskId)
  if (!ctx) return
  const startMs = Date.now()
  const agentSessionId = `tahp-adapt-agent-${taskId}`

  try {
    const userMessage = buildAdaptAgentUserMessage(ctx)
    const instructions = buildAdaptAgentInstructions(ctx, userMessage)
    const promptLog = saveAgentPromptLog(taskId, 'adapt-agent', instructions, userMessage)
    ctx.promptLogDir = promptLog.promptDir

    emit(taskId, 'task.phase', { phase: 'PREPARING', progress: 5, message: '准备 Agent 指令与 Skill 上下文...' })
    emit(taskId, 'task.plan', {
      message: `主控 Skill: ${ctx.relatedSkills[0]}；关联 ${ctx.relatedSkills.length} 个 Skill`,
      skills: ctx.relatedSkills,
    })

    emit(taskId, 'task.phase', { phase: 'CONNECTING_AGENT', progress: 12, message: '连接 Agent Bridge...' })
    getAgentBridgeManager()
    emit(taskId, 'task.step', { step_id: 'connect-agent', status: 'completed', message: 'Agent Bridge 已就绪' })

    emit(taskId, 'task.phase', { phase: 'EXECUTING', progress: 20, message: 'Agent 按 Skill SOP 执行适配...' })

    const { fullResponse } = await runAgentChat(agentSessionId, instructions, userMessage, {
      onText: (delta) => {
        ctx.llmResponse = (ctx.llmResponse || '') + delta
        emit(taskId, 'task.message', { level: 'stream', text: delta })
        if (/任务规划|当前步骤|下一步|##\s*\d/i.test(delta)) {
          const note = delta.trim().slice(0, 500)
          if (note) {
            ctx.planNotes.push(note)
            emit(taskId, 'task.plan', { message: note, partial: true })
          }
        }
      },
      onToolStarted: (toolName, args, toolCallId) => {
        if (!ctx.skillsUsed.includes(toolName)) ctx.skillsUsed.push(toolName)
        const preview = summarizeArgs(args)
        ctx.toolsUsed.push({ name: toolName, status: 'running', preview })
        emit(taskId, 'task.skill_use', {
          skill_id: toolName,
          source: 'tool_call',
          tool_call_id: toolCallId,
          args: preview,
          message: `🛠 调用: ${toolName}${preview}`,
        })
        if (FILE_WRITE_TOOLS.has(toolName) && !READ_ONLY_TOOLS.has(toolName)) {
          const filePath = extractFilePathFromArgs(args)
          if (filePath && !filePath.endsWith('SKILL.md')) {
            const action = toolName === 'write_file' || toolName === 'write' || toolName === 'Write'
              ? 'create'
              : 'modify'
            const change = { path: filePath, action, tool: toolName, at: new Date().toISOString() }
            if (!ctx.fileChanges.some(c => c.path === filePath)) {
              ctx.fileChanges.push(change)
              emit(taskId, 'task.file_change', { ...change, status: 'started' })
            }
          }
        }
      },
      onToolCompleted: (toolName, isError, toolCallId) => {
        const t = ctx.toolsUsed.find(x => x.name === toolName && x.status === 'running')
        if (t) t.status = isError ? 'error' : 'done'
        emit(taskId, 'task.tool_completed', {
          skill_id: toolName,
          tool_call_id: toolCallId,
          error: isError,
          message: isError ? `✗ 失败: ${toolName}` : `✓ 完成: ${toolName}`,
        })
      },
      onReasoning: (text) => {
        if (text?.trim()) {
          emit(taskId, 'task.message', { level: 'reasoning', text })
          emit(taskId, 'task.plan', { message: text.trim().slice(0, 800), partial: true, source: 'reasoning' })
        }
      },
    })

    const auditReport = extractAdaptAuditReport(fullResponse)
    ctx.auditReport = auditReport
    ctx.auditSkillId = ADAPT_AUDIT_SKILL_ID
    ctx.llmResponse = fullResponse
    ctx.status = 'completed'
    ctx.completedAt = new Date().toISOString()

    emit(taskId, 'task.step', {
      step_id: 'agent-run',
      status: 'completed',
      message: `Agent 完成，${fullResponse.length} 字，工具 ${ctx.toolsUsed.length} 次，文件变更 ${ctx.fileChanges.length} 项`,
    })
    if (auditReport) {
      emit(taskId, 'task.step', {
        step_id: 'self-audit',
        status: 'completed',
        message: `自检审核已写入报告末尾（${auditReport.length} 字）`,
      })
      emit(taskId, 'task.audit_completed', {
        audit_skill: ADAPT_AUDIT_SKILL_ID,
        audit_report: auditReport,
        message: '编码规范与 Skill 遵从性自检已完成',
      })
    } else {
      emit(taskId, 'task.step', {
        step_id: 'self-audit',
        status: 'warning',
        message: '未检测到报告末尾的审核章节（请确认 Agent 已 Read transsion-coding-standards-review）',
      })
    }
    emit(taskId, 'task.phase', { phase: 'COMPLETED', progress: 100, message: 'Agent 自动适配完成' })
    const reportSnapshot = {
      task_id: taskId,
      ...ctx,
      llm_response: fullResponse,
      audit_report: auditReport,
      audit_skill: ADAPT_AUDIT_SKILL_ID,
      duration_ms: Date.now() - startMs,
    }
    const normalizedFiles = extractAdaptAgentFileChanges(reportSnapshot as Record<string, unknown>)
    const normalizedSkills = extractAdaptAgentSkillRefs(reportSnapshot as Record<string, unknown>)

    emit(taskId, 'task.completed', {
      status: 'completed',
      mode: 'agent',
      response: fullResponse,
      audit_report: auditReport,
      audit_skill: ADAPT_AUDIT_SKILL_ID,
      skills_used: normalizedSkills,
      files_modified: normalizedFiles.map(c => c.path),
      duration_ms: Date.now() - startMs,
      message: auditReport ? 'Agent 自动适配完成（含末尾自检审核）' : 'Agent 自动适配完成',
    })

    try {
      writeFileSync(
        join(reportDir(), `${taskId}.json`),
        JSON.stringify({
          ...reportSnapshot,
          started_at: ctx.startedAt,
          completed_at: ctx.completedAt,
          domain: ctx.domainId,
          domain_label: ctx.domainLabel,
          files_modified: normalizedFiles.map(c => c.path),
          file_changes: normalizedFiles,
          skills_used: normalizedSkills,
          related_skills: ctx.relatedSkills,
        }, null, 2),
        'utf-8',
      )
    } catch (e) {
      logger.warn({ err: (e as Error).message, taskId }, '[adapt-agent] report write failed')
    }
  } catch (err) {
    const msg = (err as Error).message
    ctx.status = 'failed'
    ctx.error = msg
    emit(taskId, 'task.failed', { error: msg, message: `Agent 自动适配失败: ${msg}` })
  } finally {
    sharedBridgeClient.destroy(agentSessionId).catch(() => {})
  }
}

export function readAdaptAgentReport(taskId: string): unknown {
  const p = join(reportDir(), `${taskId}.json`)
  if (!existsSync(p)) return null
  try { return JSON.parse(readFileSync(p, 'utf-8')) } catch { return null }
}
