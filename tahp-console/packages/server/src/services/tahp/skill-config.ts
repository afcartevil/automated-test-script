/**
 * TAHP — 常用 Skill 配置
 *
 * 清单：{projectRoot}/.tahp/required-skills.json
 * 状态：{projectRoot}/.tahp/skill-config-state.json
 */
import { randomBytes } from 'crypto'
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'fs'
import { join } from 'path'
import { logger } from '../logger'
import { getTaskStream } from './task-stream'
import { tahpPaths } from './paths'
import {
  AgentBridgeClient,
  getAgentBridgeManager,
  type AgentBridgeOutput,
} from '../hermes/agent-bridge'
import { filterBridgeToolCallMarkupDelta } from '../hermes/run-chat/bridge-delta'
import {
  buildFullTahpSystemContext,
  getTahpSkillsRootForPrompt,
  tahpSkillMdRelativePath,
} from './context-injector'
import { saveAgentPromptLog } from './prompt-log'
import {
  APPROVAL_AUTO_ONCE_MS,
  type ApprovalRequestPayload,
} from './bug-analysis-interaction'

const sharedBridgeClient = new AgentBridgeClient({ timeoutMs: 30 * 60_000 })

// ─── 清单与状态路径 ─────────────────────────────────────────────────────────

function tahpConfigDir(): string {
  const d = join(tahpPaths.projectRoot, '.tahp')
  if (!existsSync(d)) mkdirSync(d, { recursive: true })
  return d
}

function manifestPath(): string {
  return join(tahpConfigDir(), 'required-skills.json')
}

function statePath(): string {
  return join(tahpConfigDir(), 'skill-config-state.json')
}

export type SkillConfigStatus = 'not_configured' | 'configuring' | 'configured'

export interface RequiredSkillEntry {
  id: string
  label: string
  description?: string
  depends_on?: string[]
  /** 虚拟 Skill：无 skills/.claude/skills/<id>/SKILL.md，用 setup_doc / agent_brief 引导 Agent */
  virtual?: boolean
  setup_doc?: string
  agent_brief?: string
  related_skill?: string
}

export interface RequiredSkillsManifest {
  version: number
  description?: string
  skills: RequiredSkillEntry[]
}

export interface SkillConfigStateRecord {
  status: 'configured'
  completed_at?: string
  last_task_id?: string
  note?: string
  configured_by?: 'agent' | 'manual'
}

export interface SkillConfigListItem {
  id: string
  label: string
  description?: string
  depends_on?: string[]
  status: SkillConfigStatus
  completed_at?: string
  note?: string
  active_task_id?: string
}

export interface SkillConfigPreview {
  id: string
  label: string
  description?: string
  skill_md: string
  skill_md_path: string
  manifest_path: string
}

// ─── 持久化读写 ─────────────────────────────────────────────────────────────

function readManifest(): RequiredSkillsManifest {
  const p = manifestPath()
  if (!existsSync(p)) {
    const fallback: RequiredSkillsManifest = {
      version: 1,
      skills: [
        { id: 'jira-ops', label: 'Jira 操作与日志下载' },
        { id: 'modem-analysis-local', label: 'Modem 故障分析', depends_on: ['jira-ops'] },
      ],
    }
    writeFileSync(p, JSON.stringify(fallback, null, 2), 'utf-8')
    return fallback
  }
  try {
    const json = JSON.parse(readFileSync(p, 'utf-8')) as RequiredSkillsManifest
    if (!Array.isArray(json.skills)) throw new Error('invalid manifest')
    return json
  } catch (err) {
    throw new Error(`无法解析 required-skills.json: ${(err as Error).message}`)
  }
}

function readStateMap(): Record<string, SkillConfigStateRecord> {
  const p = statePath()
  if (!existsSync(p)) return {}
  try {
    return JSON.parse(readFileSync(p, 'utf-8')) as Record<string, SkillConfigStateRecord>
  } catch {
    return {}
  }
}

function writeStateMap(map: Record<string, SkillConfigStateRecord>): void {
  writeFileSync(statePath(), JSON.stringify(map, null, 2), 'utf-8')
}

function skillRoot(skillId: string): string {
  return join(tahpPaths.skillsDir, skillId)
}

function isSkillConfiguredInState(
  state: Record<string, SkillConfigStateRecord>,
  skillId: string,
): boolean {
  const rec = state[skillId]
  if (!rec) return false
  // 兼容旧版状态文件中的 verify_failed
  return rec.status === 'configured' || (rec.status as string) === 'verify_failed'
}

function buildVirtualPreviewMd(entry: RequiredSkillEntry): string {
  const lines = [
    `# ${entry.label}`,
    '',
    entry.description ? `> ${entry.description}` : '',
    '',
    '## 配置说明（虚拟 Skill）',
    '',
    '本条目无独立 `SKILL.md`，Agent 将按下列 SOP 文档在当前主机完成安装与初始化。',
    '',
  ]
  if (entry.agent_brief) {
    lines.push('## Agent 任务', '', entry.agent_brief, '')
  }
  if (entry.setup_doc) {
    lines.push('## SOP 文档路径', '', `\`${entry.setup_doc}\``, '')
  }
  if (entry.related_skill) {
    lines.push(
      '## 参考 Skill',
      '',
      `安装完成后可参考工程内 \`harness-install\`（\`${entry.related_skill}\`）做 \`doctor\` / \`config\` 等后续配置。`,
      '',
    )
  }
  return lines.filter(Boolean).join('\n')
}

function isVirtualEntry(entry: RequiredSkillEntry): boolean {
  return entry.virtual === true
}

function getManifestEntry(skillId: string): RequiredSkillEntry | undefined {
  return readManifest().skills.find(s => s.id === skillId)
}

export function markSkillConfigured(
  skillId: string,
  opts: { taskId?: string; note?: string; by?: 'agent' | 'manual' } = {},
): void {
  const map = readStateMap()
  map[skillId] = {
    status: 'configured',
    completed_at: new Date().toISOString(),
    last_task_id: opts.taskId,
    note: opts.note || '配置完成',
    configured_by: opts.by || 'agent',
  }
  writeStateMap(map)
}

export function clearSkillConfigured(skillId: string): void {
  const map = readStateMap()
  delete map[skillId]
  writeStateMap(map)
}

export function listRequiredSkills(): {
  manifest_path: string
  skills: SkillConfigListItem[]
} {
  const manifest = readManifest()
  const state = readStateMap()
  const skills: SkillConfigListItem[] = manifest.skills.map((entry) => {
    const rec = state[entry.id]
    const active = activeTasks.get(entry.id)
    let status: SkillConfigStatus = 'not_configured'
    if (active && (active.status === 'running' || active.status === 'waiting_user')) {
      status = 'configuring'
    } else if (rec && isSkillConfiguredInState(state, entry.id)) {
      status = 'configured'
    }

    return {
      id: entry.id,
      label: entry.label,
      description: entry.description,
      depends_on: entry.depends_on,
      status,
      completed_at: rec?.completed_at,
      note: rec?.note,
      active_task_id: active?.taskId,
    }
  })
  return { manifest_path: manifestPath(), skills }
}

export function getSkillPreview(skillId: string): SkillConfigPreview | null {
  const manifest = readManifest()
  const entry = manifest.skills.find(s => s.id === skillId)
  if (!entry) return null

  if (isVirtualEntry(entry)) {
    return {
      id: skillId,
      label: entry.label,
      description: entry.description,
      skill_md: buildVirtualPreviewMd(entry),
      skill_md_path: entry.setup_doc || `(virtual:${skillId})`,
      manifest_path: manifestPath(),
    }
  }

  const mdPath = join(skillRoot(skillId), 'SKILL.md')
  if (!existsSync(mdPath)) return null
  const skillMd = readFileSync(mdPath, 'utf-8')
  return {
    id: skillId,
    label: entry.label,
    description: entry.description,
    skill_md: skillMd,
    skill_md_path: mdPath,
    manifest_path: manifestPath(),
  }
}

// ─── Agent 任务 ───────────────────────────────────────────────────────────────

interface SkillConfigTaskCtx {
  taskId: string
  skillId: string
  skillLabel: string
  forceReconfigure: boolean
  startedAt: string
  status: 'running' | 'completed' | 'failed' | 'waiting_user'
  sessionId: string
  llmResponse?: string
  error?: string
}

const taskCtx = new Map<string, SkillConfigTaskCtx>()
const activeTasks = new Map<string, SkillConfigTaskCtx>() // skillId -> ctx
const pendingApprovals = new Map<string, Map<string, { timer: ReturnType<typeof setTimeout> }>>()

function genTaskId(skillId: string): string {
  return `task-skill-config-${skillId}-${Date.now()}-${randomBytes(2).toString('hex')}`
}

function emit(taskId: string, type: string, payload: Record<string, unknown>) {
  getTaskStream().publish({
    type,
    task_id: taskId,
    payload: { task_id: taskId, ...payload },
    ts: Date.now(),
  })
}

const CONFIG_COMPLETE_RE = /=== TAHP_SKILL_CONFIG_COMPLETE ===\r?\n([\s\S]*?)=== END_TAHP_SKILL_CONFIG_COMPLETE ===/

export interface ConfiguredPeerSkillRef {
  id: string
  label: string
  isDependency: boolean
  configLocations: string[]
  completedNote?: string
}

/** 清单中已配置完成、可供当前 Skill 参考的其它条目 */
export function getConfiguredPeerSkills(currentSkillId: string): {
  peers: ConfiguredPeerSkillRef[]
  missingDependencies: Array<{ id: string; label: string }>
} {
  const manifest = readManifest()
  const state = readStateMap()
  const currentEntry = manifest.skills.find(s => s.id === currentSkillId)
  const peers: ConfiguredPeerSkillRef[] = []

  function isSkillConfigured(entry: RequiredSkillEntry): boolean {
    return isSkillConfiguredInState(state, entry.id)
  }

  for (const entry of manifest.skills) {
    if (entry.id === currentSkillId) continue
    if (!isSkillConfigured(entry)) continue

    peers.push({
      id: entry.id,
      label: entry.label,
      isDependency: currentEntry?.depends_on?.includes(entry.id) ?? false,
      configLocations: getSkillConfigLocations(entry),
      completedNote: state[entry.id]?.note,
    })
  }

  const missingDependencies: Array<{ id: string; label: string }> = []
  for (const depId of currentEntry?.depends_on ?? []) {
    const depEntry = manifest.skills.find(s => s.id === depId)
    if (!depEntry || isSkillConfigured(depEntry)) continue
    missingDependencies.push({
      id: depId,
      label: depEntry.label || depId,
    })
  }

  return { peers, missingDependencies }
}

function getSkillConfigLocations(entry: RequiredSkillEntry): string[] {
  const rel = getTahpSkillsRootForPrompt()
  const hints: string[] = []

  if (isVirtualEntry(entry)) {
    if (entry.setup_doc) hints.push(`SOP 文档: \`${entry.setup_doc}\``)
    if (entry.related_skill) {
      hints.push(`相关 Skill: \`${tahpSkillMdRelativePath(entry.related_skill)}\``)
      hints.push('`harness config show` / `harness --json doctor` 输出')
    }
    return hints
  }

  const skillRel = `${rel}/${entry.id}`
  hints.push(`\`${skillRel}/SKILL.md\``)
  hints.push(`\`${skillRel}/.env\``)
  hints.push(`\`${skillRel}/log-pipeline/.env\`（若存在）`)
  hints.push(`\`${skillRel}/\` 下 \`python scripts/api_jira.py config show\`（若适用）`)
  return hints
}

/** 首次配置时注入：引导 Agent 复用清单中已配置 Skill 的凭据与路径 */
export function buildConfiguredSkillsReferenceBlock(
  currentSkillId: string,
  currentEntry: RequiredSkillEntry,
  peerContext?: ReturnType<typeof getConfiguredPeerSkills>,
): string {
  const { peers, missingDependencies } = peerContext ?? getConfiguredPeerSkills(currentSkillId)
  if (!peers.length && !missingDependencies.length) return ''

  const lines: string[] = [
    '# 参考已配置 Skill（减少重复填写）',
    '',
    '配置清单中已有 Skill 完成配置。配置当前 Skill 前，**必须先 Read 下列已配置项的持久化存储**，复用相同或等价的系统账号、密码、工具路径（如 `JIRA_*`、`FEISHU_*`、`WORKSPACE_ROOT`、`SEVEN_ZIP_EXE`、`NETWORK_SERVERS`、harness `config` 等）。',
    '**禁止**向用户重复索要已在其它 Skill 或工程级文件中存在的凭据；仅对缺失项提问。',
    '',
    '## 工程级共享凭据（优先检查）',
    '- `.tahp/jira-user-config.json` — Console 同步的 JIRA 用户名/密码/服务器',
    '- `~/.jira_cli_config.json` — jira-ops `config set` 写入的 Jira 凭据',
    '',
  ]

  if (missingDependencies.length) {
    lines.push('## 前置依赖尚未就绪')
    for (const dep of missingDependencies) {
      lines.push(`- **${dep.label}**（\`${dep.id}\`）尚未配置完成；若当前 Skill 强依赖其能力，请先提示用户完成该依赖，或说明将单独补齐缺失项。`)
    }
    lines.push('')
  }

  if (peers.length) {
    const sorted = [...peers].sort((a, b) => {
      if (a.isDependency !== b.isDependency) return a.isDependency ? -1 : 1
      return a.label.localeCompare(b.label, 'zh-CN')
    })
    lines.push('## 已配置 Skill 参考清单')
    for (const peer of sorted) {
      const depTag = peer.isDependency ? '（**本 Skill 依赖项，优先参考**）' : ''
      lines.push(`### ${peer.label}（\`${peer.id}\`）${depTag}`)
      if (peer.completedNote) lines.push(`- 配置摘要: ${peer.completedNote}`)
      lines.push('- 建议 Read 的配置位置:')
      for (const loc of peer.configLocations) {
        lines.push(`  - ${loc}`)
      }
      lines.push('')
    }
  }

  const currentDeps = currentEntry.depends_on ?? []
  if (currentDeps.length && peers.some(p => p.isDependency)) {
    lines.push(
      '## 复用规则',
      `- 当前 Skill（\`${currentSkillId}\`）声明依赖: ${currentDeps.map(d => `\`${d}\``).join('、')}`,
      '- 从依赖 Skill 的 `.env` / `config show` 中读取到的 `JIRA_SERVER`、`JIRA_USERNAME`、`JIRA_PASSWORD`、`WORKSPACE_ROOT` 等，应直接写入当前 Skill 规定的存储位置（如 `.env`、`log-pipeline/.env`、`config set`），无需用户再次输入。',
      '- 写入后运行当前 Skill 的体检命令确认；若某项在依赖 Skill 中也不存在，再向用户索取。',
      '',
    )
  }

  return lines.join('\n')
}

function parseConfigCompleteMarker(text: string): { skillId?: string; message?: string } | null {
  const m = CONFIG_COMPLETE_RE.exec(text)
  if (!m) return null
  const fields: Record<string, string> = {}
  for (const line of m[1].split(/\r?\n/)) {
    const idx = line.indexOf(':')
    if (idx <= 0) continue
    fields[line.slice(0, idx).trim().toLowerCase()] = line.slice(idx + 1).trim()
  }
  return { skillId: fields.skill_id, message: fields.message }
}

function buildSkillConfigInstructions(
  entry: RequiredSkillEntry,
  force: boolean,
  peerContext?: ReturnType<typeof getConfiguredPeerSkills>,
): string {
  const skillId = entry.id
  const skillLabel = entry.label
  const rel = getTahpSkillsRootForPrompt()
  const resolvedPeerContext = force
    ? { peers: [], missingDependencies: [] }
    : (peerContext ?? getConfiguredPeerSkills(skillId))

  let base: string
  if (isVirtualEntry(entry)) {
    const relatedPath = entry.related_skill ? tahpSkillMdRelativePath(entry.related_skill) : ''
    base = `你是 TAHP「常用 Skill 配置」向导，负责在**当前主机**完成 **${skillLabel}**（\`${skillId}\`，虚拟配置项）的安装与初始化。

# 必须遵守
1. **先 Read** 内网 SOP 文档（UNC/文件路径）：\`${entry.setup_doc || '(见 agent_brief)'}\`
   - 若路径为 Windows UNC（\\\\server\\share\\...），用 Read 工具直接读取；不可访问时向用户说明并请求可复制到本地的路径。
2. **严格执行 SOP**：${entry.agent_brief || '按 SOP 安装 transsion harness'}
3. 在**当前主机**完成：Node/npm 环境检查、harness 包安装、\`harness install\`、\`harness agent install-skill\`（若 SOP 要求）及 \`harness doctor\` 复核。
4. 缺少必填参数时一次性列出格式示例；收到用户回复后立即执行安装/配置命令，不要只记在对话里。
5. 每完成一阶段运行 \`harness --json doctor\`（或 SOP 指定命令）验证。
6. **全部步骤完成且 doctor 通过后**，输出完成标记块（见下文），并总结安装版本与关键路径。
${entry.related_skill ? `7. 可参考工程 Skill \`${relatedPath}\`（\`${entry.related_skill}\`）处理后续 config / setup-env。` : ''}
${force ? '\n# 重新配置模式\n用户要求**覆盖/重新安装**，请先检查现有 harness 版本与安装路径，再按 SOP 重新执行。' : ''}

# 完成标记（doctor 通过后必须输出）
\`\`\`
=== TAHP_SKILL_CONFIG_COMPLETE ===
skill_id: ${skillId}
status: success
message: <一句话说明 harness 安装与 doctor 结果>
=== END_TAHP_SKILL_CONFIG_COMPLETE ===
\`\`\`
`
  } else {
    const skillPath = tahpSkillMdRelativePath(skillId)
    base = `你是 TAHP「常用 Skill 配置」向导，负责引导用户完成 **${skillLabel}**（\`${skillId}\`）的全部必要环境配置。

# 必须遵守
1. **先 Read** Skill 全文：\`${skillPath}\`，严格按其中「首次使用 / 环境 / Step 0」等章节执行。
2. 缺少必填项时，**一次性**列出所需参数与格式示例，请用户按格式回复；收到后**立即写入持久化存储**（\`.env\`、\`config set\`、\`env set\` 等，按 Skill 规定），不要只记在对话里。
3. 每完成一类配置后运行 Skill 文档中的体检命令（如 \`setup-check\`），根据结果继续或修复。
4. **全部必填配置完成且体检通过后**，输出完成标记块（见下文），然后简短总结已配置项。
5. 使用中文与用户沟通；敏感值（密码）提示用户可直接在对话提供，你会写入安全存储。
${force ? '\n# 重新配置模式\n用户要求**覆盖/重新配置**，请先说明将检查并更新哪些项，再逐项引导。' : ''}

# 完成标记（体检全部通过后必须输出）
\`\`\`
=== TAHP_SKILL_CONFIG_COMPLETE ===
skill_id: ${skillId}
status: success
message: <一句话说明配置结果>
=== END_TAHP_SKILL_CONFIG_COMPLETE ===
\`\`\`

# Skill 根目录（相对工程）
\`${rel}/${skillId}/\`
`
  }

  const referenceBlock = force ? '' : buildConfiguredSkillsReferenceBlock(skillId, entry, resolvedPeerContext)
  if (referenceBlock) {
    base = `${base}\n\n${referenceBlock}`
  }

  const userHint = force
    ? `请引导我重新完成 ${skillLabel} 的全部必要配置（可覆盖已有配置）。`
    : entry.agent_brief || `请引导我完成 ${skillLabel} 的全部必要配置。`
  const preferred = [
    ...resolvedPeerContext.peers.map(p => p.id),
    ...(entry.depends_on ?? []),
    entry.related_skill,
    skillId,
  ].filter(Boolean) as string[]
  const tahpCtx = buildFullTahpSystemContext(userHint, {
    scenario: 'skill_config',
    preferredSkillIds: [...new Set(preferred)],
  })
  return tahpCtx ? `${base}\n\n${tahpCtx}` : base
}

function registerApproval(taskId: string, payload: ApprovalRequestPayload) {
  let bucket = pendingApprovals.get(taskId)
  if (!bucket) {
    bucket = new Map()
    pendingApprovals.set(taskId, bucket)
  }
  if (bucket.has(payload.approval_id)) return
  const timeoutMs = payload.timeout_ms || APPROVAL_AUTO_ONCE_MS
  emit(taskId, 'task.approval_requested', {
    approval_id: payload.approval_id,
    command: payload.command,
    description: payload.description,
    choices: payload.choices,
    timeout_ms: timeoutMs,
    deadline_at: Date.now() + timeoutMs,
    auto_action: 'once',
  })
  const timer = setTimeout(() => {
    void sharedBridgeClient.approvalRespond(payload.approval_id, 'once').catch(() => {})
  }, timeoutMs)
  bucket.set(payload.approval_id, { timer })
}

async function runAgentTurn(
  ctx: SkillConfigTaskCtx,
  userMessage: string,
  options: { instructions?: string; conversationHistory?: unknown[] },
): Promise<string> {
  const manager = getAgentBridgeManager()
  if (!manager.running) {
    throw new Error('Agent Bridge 未运行，请检查 hermes CLI 与 agent-bridge')
  }

  const started = await sharedBridgeClient.chat(
    ctx.sessionId,
    userMessage,
    options.conversationHistory,
    options.instructions,
    'default',
  )

  const markupState: { bridgePendingToolCallMarkup?: string } = {}
  let fullResponse = ''
  let lastChunk: AgentBridgeOutput | null = null

  for await (const chunk of sharedBridgeClient.streamOutput(started.run_id, { intervalMs: 100 })) {
    lastChunk = chunk
    for (const ev of chunk.events || []) {
      const evType = ev.event as string | undefined
      if (evType === 'approval.requested') {
        registerApproval(ctx.taskId, {
          approval_id: String(ev.approval_id || ''),
          command: String(ev.command || ''),
          description: String(ev.description || ''),
          choices: Array.isArray(ev.choices) ? ev.choices.map(String) : ['once', 'deny'],
          timeout_ms: typeof ev.timeout_ms === 'number' ? ev.timeout_ms : APPROVAL_AUTO_ONCE_MS,
        })
      }
    }
    if (chunk.delta) {
      const cleaned = filterBridgeToolCallMarkupDelta(markupState, chunk.delta)
      if (cleaned) {
        fullResponse += cleaned
        emit(ctx.taskId, 'task.message', { level: 'stream', text: cleaned })
      }
    }
    if (chunk.done) {
      if (chunk.status === 'error') throw new Error(chunk.error || 'Agent 运行出错')
      if (chunk.status === 'interrupted') throw new Error('Agent 运行被中断')
      break
    }
  }
  if (!lastChunk?.done) throw new Error('Agent 流意外终止')
  return fullResponse
}

async function executeSkillConfigRun(
  ctx: SkillConfigTaskCtx,
  userMessage: string,
  isContinue: boolean,
  peerContext?: ReturnType<typeof getConfiguredPeerSkills>,
): Promise<void> {
  try {
    const entry = getManifestEntry(ctx.skillId)
    const instructions = isContinue || !entry
      ? undefined
      : buildSkillConfigInstructions(entry, ctx.forceReconfigure, peerContext)

    if (!isContinue) {
      saveAgentPromptLog(ctx.taskId, 'skill-config', instructions || '', userMessage)
    }

    emit(ctx.taskId, 'task.phase', {
      phase: 'CONFIGURING',
      progress: 30,
      skill_id: ctx.skillId,
      message: isContinue ? '继续配置对话...' : 'Agent 正在引导配置...',
    })

    const fullResponse = await runAgentTurn(ctx, userMessage, { instructions })
    ctx.llmResponse = (ctx.llmResponse || '') + fullResponse

    const complete = parseConfigCompleteMarker(fullResponse)
    if (complete) {
      markSkillConfigured(ctx.skillId, {
        taskId: ctx.taskId,
        note: complete.message,
        by: 'agent',
      })
      ctx.status = 'completed'
      const message = complete.message || '配置完成'
      emit(ctx.taskId, 'task.skill_config_complete', {
        skill_id: ctx.skillId,
        message,
      })
      emit(ctx.taskId, 'task.completed', {
        status: 'completed',
        skill_id: ctx.skillId,
        message: 'Skill 配置向导完成',
      })
      activeTasks.delete(ctx.skillId)
      return
    }

    ctx.status = 'waiting_user'
    emit(ctx.taskId, 'task.phase', {
      phase: 'WAITING_USER',
      progress: 60,
      skill_id: ctx.skillId,
      message: '等待您在下方输入补充信息或配置值',
    })
  } catch (err) {
    const msg = (err as Error).message
    ctx.status = 'failed'
    ctx.error = msg
    emit(ctx.taskId, 'task.failed', { error: msg, skill_id: ctx.skillId, message: msg })
    activeTasks.delete(ctx.skillId)
    logger.warn({ err: msg, taskId: ctx.taskId }, '[skill-config] failed')
  } finally {
    const bucket = pendingApprovals.get(ctx.taskId)
    if (bucket) {
      for (const e of bucket.values()) clearTimeout(e.timer)
      pendingApprovals.delete(ctx.taskId)
    }
  }
}

export function startSkillConfigAgent(skillId: string, force = false): {
  ok: boolean
  taskId?: string
  error?: string
} {
  const manifest = readManifest()
  const entry = manifest.skills.find(s => s.id === skillId)
  if (!entry) return { ok: false, error: `清单中无 Skill: ${skillId}` }
  if (!isVirtualEntry(entry) && !existsSync(join(skillRoot(skillId), 'SKILL.md'))) {
    return { ok: false, error: `Skill 不存在: ${skillId}` }
  }

  const existing = activeTasks.get(skillId)
  if (existing?.status === 'running' || existing?.status === 'waiting_user') {
    return { ok: false, error: '该 Skill 配置任务进行中，请先在对话区继续或等待结束' }
  }

  if (force) clearSkillConfigured(skillId)

  const taskId = genTaskId(skillId)
  const sessionId = `tahp-skill-config-${skillId}`
  const ctx: SkillConfigTaskCtx = {
    taskId,
    skillId,
    skillLabel: entry.label,
    forceReconfigure: force,
    startedAt: new Date().toISOString(),
    status: 'running',
    sessionId,
  }
  taskCtx.set(taskId, ctx)
  activeTasks.set(skillId, ctx)

  const peerContext = force ? { peers: [], missingDependencies: [] } : getConfiguredPeerSkills(skillId)
  const peerHint = force
    ? ''
    : (peerContext.peers.length
      ? `请先参考配置清单中已完成的 Skill：${peerContext.peers.map(p => `${p.label}（${p.id}）`).join('、')}，复用其中已有的系统账号、密码与工具路径，避免重复向我索要。`
      : '')
  const userMessage = force
    ? `请引导我**重新配置** ${entry.label}（${skillId}）的全部必要项，可覆盖已有配置。`
    : [peerHint, entry.agent_brief || `请引导我完成 ${entry.label}（${skillId}）的全部必要配置。`]
      .filter(Boolean)
      .join('\n')

  emit(taskId, 'task.started', {
    type: 'skill_config',
    skill_id: skillId,
    skill_label: entry.label,
    force,
    message: `开始配置: ${entry.label}`,
  })

  setImmediate(() => {
    executeSkillConfigRun(ctx, userMessage, false, peerContext).catch(() => {})
  })

  return { ok: true, taskId }
}

export function continueSkillConfigAgent(taskId: string, message: string): {
  ok: boolean
  error?: string
} {
  const text = message.trim()
  if (!text) return { ok: false, error: '消息不能为空' }

  const ctx = taskCtx.get(taskId)
  if (!ctx) return { ok: false, error: `找不到任务: ${taskId}` }
  if (ctx.status !== 'waiting_user' && ctx.status !== 'running') {
    return { ok: false, error: `任务状态不可继续: ${ctx.status}` }
  }

  ctx.status = 'running'
  activeTasks.set(ctx.skillId, ctx)
  emit(taskId, 'task.message', {
    level: 'user',
    text: `\n\n**用户**\n\n${text}\n\n`,
  })

  setImmediate(() => {
    executeSkillConfigRun(ctx, text, true).catch(() => {})
  })

  return { ok: true }
}

export async function respondSkillConfigApproval(
  taskId: string,
  approvalId: string,
  choice: string,
): Promise<{ ok: boolean; error?: string }> {
  try {
    await sharedBridgeClient.approvalRespond(approvalId, choice)
    emit(taskId, 'task.approval_resolved', { approval_id: approvalId, choice })
    const bucket = pendingApprovals.get(taskId)
    const entry = bucket?.get(approvalId)
    if (entry) {
      clearTimeout(entry.timer)
      bucket?.delete(approvalId)
    }
    return { ok: true }
  } catch (err) {
    return { ok: false, error: (err as Error).message }
  }
}

export function getSkillConfigTask(taskId: string): SkillConfigTaskCtx | undefined {
  return taskCtx.get(taskId)
}

export { manifestPath as getRequiredSkillsManifestPath }
