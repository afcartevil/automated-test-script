/**
 * TAHP 任务 REST 路由
 *
 * POST /api/tahp/tasks — 启动任务
 *   · document_path='__inline__' → 直接调用已配置的大模型（无需 Python MCP 服务）
 *   · 其他 document_path        → 通过 Python MCP 桥调用 tahp_execute
 */
import Router from '@koa/router'
import type { Context } from 'koa'
import { randomBytes } from 'crypto'
import { existsSync, readFileSync, writeFileSync, readdirSync, mkdirSync } from 'fs'
import { join, dirname } from 'path'
import { getMcpBridge } from '../../services/tahp/mcp-bridge'
import { getTaskStream } from '../../services/tahp/task-stream'
import { tahpPaths } from '../../services/tahp/paths'
import { logger } from '../../services/logger'
import { resolveGatewayUpstream } from '../../services/hermes/run-chat/handle-api-run'

// ─── 内联任务上下文缓存（供纠偏重跑使用）────────────────────────────────────────
interface InlineTaskCtx {
  module: string
  domain: string
  documentContent: string
  extraContext?: string
  prevResponse?: string      // 上次 LLM 输出，纠偏时追加到 prompt
  corrections: string[]      // 历次纠偏反馈
}
const inlineTaskCtx = new Map<string, InlineTaskCtx>()

export const tahpTaskRoutes = new Router()

// ─── 工具函数 ────────────────────────────────────────────────────────────────

interface ToolCallResult {
  content?: Array<{ type: string; text?: string }>
  isError?: boolean
}

function unwrapToolResult(raw: unknown): unknown {
  const r = raw as ToolCallResult
  if (!r || !Array.isArray(r.content)) return raw
  const first = r.content[0]
  if (!first || first.type !== 'text') return r
  try { return JSON.parse(first.text || '') } catch { return { text: first.text } }
}

async function callTool(ctx: Context, name: string, args: Record<string, unknown>) {
  try {
    const raw = await getMcpBridge().callTool(name, args)
    ctx.body = { success: true, data: unwrapToolResult(raw) }
  } catch (err) {
    logger.warn({ err: (err as Error).message, name }, '[tahp-task] tool call failed')
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
}

function genTaskId(): string {
  return `task-adapt-${Date.now()}-${randomBytes(3).toString('hex')}`
}

// ─── 约束摘要（从磁盘读取，无需 Python）───────────────────────────────────────

function loadConstraintsSummary(module: string): string {
  const moduleDir = join(tahpPaths.constraintsDir, module)
  if (!existsSync(moduleDir)) return '(约束文件目录不存在，跳过约束加载)'
  const lines: string[] = []
  try {
    for (const f of readdirSync(moduleDir)) {
      if (!f.endsWith('.yaml')) continue
      const content = readFileSync(join(moduleDir, f), 'utf-8')
      lines.push(`### ${f}\n\`\`\`yaml\n${content.slice(0, 2000)}${content.length > 2000 ? '\n...(截断)' : ''}\n\`\`\``)
    }
  } catch { /* ignore */ }
  return lines.length ? lines.join('\n\n') : '(无约束文件)'
}

// 读取动态技能的 SKILL.md 内容
function loadSkillContent(skillId: string): string {
  const skillMd = join(tahpPaths.projectRoot, 'skills', '.claude', 'skills', skillId, 'SKILL.md')
  if (!existsSync(skillMd)) return ''
  try { return readFileSync(skillMd, 'utf-8').slice(0, 4000) } catch { return '' }
}

// ─── LLM 流式调用（不依赖 Python，直接调用配置的大模型）─────────────────────

async function* streamLLMResponse(
  upstream: string,
  apiKey: string | undefined,
  providerType: string,
  systemPrompt: string,
  userPrompt: string,
  defaultModel?: string,
): AsyncGenerator<string> {
  const isAnthropic = upstream === 'anthropic://direct' || providerType === 'anthropic'
  // Strip trailing slash and any trailing /v1 (or /v2 etc.) to avoid double-path like /v1/v1/chat/completions
  const upstreamBase = upstream.replace(/\/+$/, '').replace(/\/v\d+$/, '')
  const endpoint = isAnthropic
    ? 'https://api.anthropic.com/v1/messages'
    : `${upstreamBase}/v1/chat/completions`

  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (isAnthropic) {
    headers['x-api-key'] = apiKey || ''
    headers['anthropic-version'] = '2023-06-01'
  } else {
    if (apiKey) headers['Authorization'] = `Bearer ${apiKey}`
  }

  const model = defaultModel || (isAnthropic ? 'claude-3-5-sonnet-20241022' : 'gpt-4o')
  const body = isAnthropic
    ? JSON.stringify({
        model, max_tokens: 4096, stream: true,
        system: systemPrompt,
        messages: [{ role: 'user', content: userPrompt }],
      })
    : JSON.stringify({
        model, stream: true,
        messages: [
          { role: 'system', content: systemPrompt },
          { role: 'user', content: userPrompt },
        ],
      })

  const resp = await fetch(endpoint, { method: 'POST', headers, body })
  if (!resp.ok || !resp.body) {
    const text = await resp.text().catch(() => resp.statusText)
    throw new Error(`LLM API 错误 ${resp.status}: ${text}`)
  }

  const reader = resp.body.getReader()
  const dec = new TextDecoder()
  let buf = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += dec.decode(value, { stream: true })
    const lines = buf.split('\n')
    buf = lines.pop() ?? ''
    for (const line of lines) {
      const trimmed = line.trim()
      if (!trimmed.startsWith('data:')) continue
      const data = trimmed.slice(5).trim()
      if (data === '[DONE]') return
      try {
        const parsed = JSON.parse(data)
        // Anthropic format
        if (parsed.type === 'content_block_delta' && parsed.delta?.type === 'text_delta') {
          yield parsed.delta.text || ''
        }
        // OpenAI format
        else if (parsed.choices?.[0]?.delta?.content) {
          yield parsed.choices[0].delta.content
        }
      } catch { /* ignore malformed SSE lines */ }
    }
  }
}

// ─── 文件路径提取（从文档内容中识别用户填写的文件路径）─────────────────────────

function extractFilePaths(documentContent: string): string[] {
  const paths: string[] = []
  // 匹配常见文件路径格式：- 字段名: /path 或 C:\path
  const re = /[-:：]\s*((?:[A-Za-z]:[\\/]|\/)[^\s\n,，]+\.[a-zA-Z0-9]+)/g
  let m: RegExpExecArray | null
  while ((m = re.exec(documentContent)) !== null) {
    const p = m[1].trim()
    if (existsSync(p)) paths.push(p)
  }
  return [...new Set(paths)]
}

// ─── 解析 LLM 响应中的文件修改块并写入磁盘 ─────────────────────────────────────

interface FileChange { path: string; content: string }

function parseAndApplyFileChanges(response: string): FileChange[] {
  const changes: FileChange[] = []

  // 同时支持两种格式，兼容 LLM 输出差异
  const patterns = [
    // 格式1（XML，最稳定）：<write_file><path>...</path><content>...</content></write_file>
    /<write_file>\s*<path>([\s\S]+?)<\/path>\s*<content>([\s\S]*?)<\/content>\s*<\/write_file>/g,
    // 格式2（宽松尖括号）：<<<MODIFY_FILE: path>>> ... <<<END_MODIFY>>> （允许2~4个>）
    /<<<MODIFY_FILE:\s*(.+?)>{2,4}([\s\S]*?)<<<END_MODIFY>{2,4}/g,
  ]

  for (const re of patterns) {
    let m: RegExpExecArray | null
    re.lastIndex = 0
    while ((m = re.exec(response)) !== null) {
      const filePath = m[1].trim()
      const content  = m[2].replace(/^\n/, '').replace(/\n$/, '')
      // 同一文件只写一次（以先匹配的为准）
      if (changes.find(c => c.path === filePath)) continue
      try {
        mkdirSync(dirname(filePath), { recursive: true })
        writeFileSync(filePath, content, 'utf-8')
        changes.push({ path: filePath, content })
        logger.info({ filePath }, '[tahp-llm] file written by LLM')
      } catch (e) {
        logger.warn({ filePath, err: (e as Error).message }, '[tahp-llm] failed to write file')
      }
    }
  }
  return changes
}

// ─── 内联 LLM 任务执行（核心）────────────────────────────────────────────────

async function runLLMAdaptTask(
  taskId: string,
  module: string,
  domain: string,
  documentContent: string,
  extraContext: string | undefined,
  correctionFeedback?: string,   // 纠偏场景：追加的用户反馈
  prevResponse?: string,         // 纠偏场景：上次 LLM 输出
): Promise<void> {
  const startTime = Date.now()
  const startedAt = new Date().toISOString()

  const emit = (type: string, payload: Record<string, unknown>) => {
    getTaskStream().publish({ type, task_id: taskId, payload: { task_id: taskId, ...payload }, ts: Date.now() })
  }

  // 立即存储上下文（供后续纠偏使用）
  const ctx: InlineTaskCtx = {
    module, domain, documentContent, extraContext,
    prevResponse,
    corrections: correctionFeedback ? [correctionFeedback] : [],
  }
  inlineTaskCtx.set(taskId, ctx)

  try {
    // ── Phase 1: 加载约束 ─────────────────────────────────────────────
    emit('task.phase', { phase: 'LOADING_CONSTRAINTS', progress: 5, message: '正在加载约束文件...' })
    const constraintsSummary = loadConstraintsSummary(module)
    emit('task.step', { step_id: 'load-constraints', status: 'completed', message: `模块 ${module} 约束已加载` })

    // ── Phase 2: 读取文件内容 + 加载 Skill ──────────────────────────────
    emit('task.phase', { phase: 'ANALYZING_DOCUMENT', progress: 15, message: '正在分析文件与适配上下文...' })

    // 从表单参数中提取文件路径并读取内容
    const filePaths = extractFilePaths(documentContent)
    let fileContentsBlock = ''
    for (const fp of filePaths) {
      try {
        const content = readFileSync(fp, 'utf-8')
        fileContentsBlock += `\n### 文件内容: ${fp}\n\`\`\`\n${content.slice(0, 8000)}${content.length > 8000 ? '\n...(内容截断)' : ''}\n\`\`\`\n`
        emit('task.message', { level: 'info', text: `已读取文件: ${fp} (${content.length} 字节)` })
      } catch (e) {
        emit('task.message', { level: 'warn', text: `无法读取文件: ${fp}` })
      }
    }

    // 加载关联 Skill 内容
    let skillContent = ''
    const skillSection = documentContent.match(/### 关联 Skills\n([\s\S]+?)(?:\n---|\n###|$)/)
    if (skillSection) {
      const skillIds = skillSection[1].match(/^- (.+)$/mg)?.map(l => l.slice(2).trim()) || []
      for (const sid of skillIds.slice(0, 3)) {
        const content = loadSkillContent(sid)
        if (content) skillContent += `\n## Skill: ${sid}\n${content}\n`
      }
    }
    emit('task.step', {
      step_id: 'analyze-document', status: 'completed',
      message: `已读取 ${filePaths.length} 个文件, 关联技能: ${skillContent ? '已加载' : '无'}`,
    })

    // ── Phase 3: 解析 LLM 上游 ─────────────────────────────────────────
    emit('task.phase', { phase: 'GENERATING_PLAN', progress: 25, message: '正在连接大模型...' })
    const gwConfig = resolveGatewayUpstream('default')
    if (!gwConfig.apiKey && gwConfig.upstream.includes('127.0.0.1:8642')) {
      throw new Error('未配置大模型 API。请在"模型管理"页面配置 API Key，或设置环境变量 EASY_ADAPTER_LLM_UPSTREAM 和 EASY_ADAPTER_API_KEY')
    }
    emit('task.message', { level: 'info', text: `使用模型: ${gwConfig.defaultModel || '默认'} (${gwConfig.providerType})` })
    emit('task.step', { step_id: 'generate-plan', status: 'completed', message: `已连接 ${gwConfig.providerType} 上游` })

    // ── Phase 4: 调用大模型 ────────────────────────────────────────────
    const isCorrecting = !!correctionFeedback
    emit('task.phase', {
      phase: 'EXECUTING_PIPELINE', progress: 35,
      message: isCorrecting ? '根据纠偏反馈重新执行...' : '大模型执行中，请稍候...',
    })

    // 系统提示：明确要求输出文件修改块
    const systemPrompt = `你是 EasyAdapter 的 Android BSP 适配 AI 助手，专注于 TECNO 传音设备的底软模块适配。

## 核心执行要求 — 文件修改输出格式
如果任务涉及修改文件，你**必须**使用以下 XML 格式输出完整的修改后内容，系统将自动将其写入磁盘：

<write_file>
<path>文件的完整绝对路径（例如 E:/temp/1.txt）</path>
<content>
修改后的完整文件内容（完整替换，不是 diff）
</content>
</write_file>

规则：
- path 必须是原始文件的完整绝对路径，照抄用户提供的路径，不要修改
- content 中写完整文件内容，不要省略未修改的行
- 可以在 write_file 前后写简短说明
- 多个文件依次输出多个 write_file 块

## 模块约束规范（${module}）
${constraintsSummary.slice(0, 2000)}
${skillContent ? `\n## 关联技能说明\n${skillContent.slice(0, 1500)}` : ''}
${extraContext ? `\n## 任务附加上下文\n${extraContext}` : ''}`

    // 用户提示：适配任务 + 文件内容 + 上次回复（纠偏时）+ 纠偏意见
    let userPrompt = documentContent
    if (fileContentsBlock) {
      userPrompt += `\n\n## 相关文件当前内容\n${fileContentsBlock}`
    }
    if (prevResponse) {
      userPrompt += `\n\n## 上次执行结果（供参考）\n${prevResponse.slice(0, 3000)}`
    }
    if (correctionFeedback) {
      userPrompt += `\n\n## 纠偏指令（请严格按此要求重新执行）\n${correctionFeedback}`
    }

    let fullResponse = ''
    try {
      for await (const chunk of streamLLMResponse(
        gwConfig.upstream, gwConfig.apiKey, gwConfig.providerType,
        systemPrompt, userPrompt, gwConfig.defaultModel,
      )) {
        fullResponse += chunk
        emit('task.message', { level: 'stream', text: chunk })
      }
    } catch (llmErr) {
      throw new Error(`大模型调用失败: ${(llmErr as Error).message}`)
    }

    emit('task.step', {
      step_id: 'execute-pipeline', status: 'completed',
      message: `AI 执行完成，共 ${fullResponse.length} 字`,
    })

    // ── Phase 5: 解析并写入文件修改 ────────────────────────────────────
    emit('task.phase', { phase: 'RUNNING_GATE_CHECK', progress: 90, message: '正在应用文件修改...' })
    const changes = parseAndApplyFileChanges(fullResponse)
    if (changes.length > 0) {
      emit('task.message', {
        level: 'info',
        text: `✅ 已修改 ${changes.length} 个文件:\n${changes.map(c => `  · ${c.path}`).join('\n')}`,
      })
    }
    emit('task.step', {
      step_id: 'gate-check', status: 'completed',
      message: changes.length > 0 ? `已写入 ${changes.length} 个文件` : '适配分析完成（无文件写入）',
    })

    // 更新存储的上下文（下次纠偏可用）
    ctx.prevResponse = fullResponse

    const completedAt  = new Date().toISOString()
    const durationMs   = Date.now() - startTime
    const filesModified = changes.map(c => c.path)

    emit('task.completed', {
      status:   'completed',
      response: fullResponse,
      module, domain,
      filesModified,
      started_at:   startedAt,
      completed_at: completedAt,
      duration_ms:  durationMs,
      message: changes.length > 0
        ? `AI 适配完成，已修改 ${changes.length} 个文件`
        : 'AI 适配分析完成',
    })

    // ── 写入报告文件（reports/<taskId>.json）──────────────────────────
    try {
      const reportDir = join(tahpPaths.projectRoot, 'reports')
      mkdirSync(reportDir, { recursive: true })
      const report = {
        task_id:          taskId,
        module,
        domain,
        started_at:       startedAt,
        completed_at:     completedAt,
        duration_ms:      durationMs,
        extra_context:    extraContext,
        correction_of:    correctionFeedback ? 'correction' : undefined,
        document_content: documentContent.slice(0, 5000),
        files_modified:   filesModified,
        llm_response:     fullResponse,
      }
      writeFileSync(join(reportDir, `${taskId}.json`), JSON.stringify(report, null, 2), 'utf-8')
      logger.info({ taskId, reportDir }, '[tahp-llm] report written')
    } catch (re) {
      logger.warn({ err: (re as Error).message }, '[tahp-llm] report write failed')
    }

    logger.info({ taskId, module, chars: fullResponse.length, files: changes.length }, '[tahp-llm] task completed')

  } catch (err) {
    const msg = (err as Error).message
    logger.warn({ taskId, err: msg }, '[tahp-llm] task failed')
    emit('task.failed', { error: msg, message: `适配任务失败: ${msg}` })
  }
}

// ─── 路由 ─────────────────────────────────────────────────────────────────────

// POST /api/tahp/tasks — 启动任务
tahpTaskRoutes.post('/api/tahp/tasks', async (ctx) => {
  const body = (ctx.request.body || {}) as Record<string, unknown>
  const {
    document_path,
    module,
    domain,
    constraints_extra,
    document_content,
    extra_context,
  } = body

  if (!document_path || !module || !domain) {
    ctx.status = 400
    ctx.body = { success: false, error: '缺少必填: document_path / module / domain' }
    return
  }

  // ── 内联模式：直接调用大模型，不依赖 Python MCP ──────────────────────
  if (document_path === '__inline__' && document_content) {
    const taskId = genTaskId()

    // 立即返回 task_id，异步执行 LLM 任务
    ctx.body = { success: true, data: { task_id: taskId, status: 'starting', module, domain } }

    // 发送启动信号
    getTaskStream().publish({
      type: 'task.started',
      task_id: taskId,
      payload: { task_id: taskId, document_path: '__inline__', module: String(module), domain: String(domain), message: '内联 AI 适配任务已启动' },
      ts: Date.now(),
    })

    // 异步运行，不阻塞 HTTP 响应
    setImmediate(() => {
      runLLMAdaptTask(
        taskId,
        String(module),
        String(domain),
        String(document_content),
        extra_context ? String(extra_context) : undefined,
      ).catch(e => logger.error({ e, taskId }, '[tahp-llm] unhandled'))
    })
    return
  }

  // ── 标准模式：通过 Python MCP 桥 ─────────────────────────────────────
  const mcpArgs: Record<string, unknown> = { document_path, module, domain }
  if (constraints_extra !== undefined) mcpArgs.constraints_extra = constraints_extra
  if (document_content)               mcpArgs.document_content   = document_content
  if (extra_context)                  mcpArgs.extra_context      = extra_context

  try {
    const raw  = await getMcpBridge().callTool('tahp_execute', mcpArgs)
    const data = unwrapToolResult(raw) as Record<string, unknown>
    const taskId = (data?.task_id || data?.taskId) as string | undefined

    if (taskId) {
      getTaskStream().publish({
        type: 'task.started', task_id: taskId,
        payload: { task_id: taskId, document_path: String(document_path), module: String(module), domain: String(domain), message: `任务已启动: ${taskId}` },
        ts: Date.now(),
      })
    }
    ctx.body = { success: true, data }
  } catch (err) {
    const errMsg = (err as Error).message
    getTaskStream().publish({
      type: 'task.failed', task_id: 'unknown',
      payload: { error: errMsg, message: `任务启动失败: ${errMsg}` },
      ts: Date.now(),
    })
    ctx.status = 500
    ctx.body = { success: false, error: errMsg }
  }
})

// GET /api/tahp/tasks — 列出任务
tahpTaskRoutes.get('/api/tahp/tasks', async (ctx) => {
  const includeCompleted = ctx.query.include_completed !== 'false'
  await callTool(ctx, 'tahp_list_tasks', { include_completed: includeCompleted })
})

// GET /api/tahp/tasks/:id — 任务详情
tahpTaskRoutes.get('/api/tahp/tasks/:id', async (ctx) => {
  await callTool(ctx, 'tahp_status', { task_id: ctx.params.id })
})

// POST /api/tahp/tasks/:id/correct — 纠偏（内联模式：不依赖 Python）
tahpTaskRoutes.post('/api/tahp/tasks/:id/correct', async (ctx) => {
  const body = (ctx.request.body || {}) as Record<string, unknown>
  const feedback = body.feedback
  if (typeof feedback !== 'string' || !feedback.trim()) {
    ctx.status = 400
    ctx.body = { success: false, error: '缺少 feedback' }
    return
  }

  const origTaskId = ctx.params.id
  const origCtx = inlineTaskCtx.get(origTaskId)

  // 如果找不到内联上下文，说明是 Python 任务，走原来的 MCP 路由
  if (!origCtx) {
    await callTool(ctx, 'tahp_correct', { task_id: origTaskId, feedback })
    return
  }

  // 生成新任务 ID
  const newTaskId = genTaskId()

  ctx.body = {
    success: true,
    data: {
      task_id: newTaskId,
      status: 'starting',
      correction_of: origTaskId,
      module: origCtx.module,
      domain: origCtx.domain,
    },
  }

  // 发启动信号
  getTaskStream().publish({
    type: 'task.started',
    task_id: newTaskId,
    payload: {
      task_id: newTaskId,
      document_path: '__inline__',
      module: origCtx.module,
      domain: origCtx.domain,
      correction_of: origTaskId,
      message: `纠偏任务已启动: ${feedback.slice(0, 50)}`,
    },
    ts: Date.now(),
  })

  // 异步执行纠偏（带上原始上下文 + 本次反馈）
  setImmediate(() => {
    runLLMAdaptTask(
      newTaskId,
      origCtx.module,
      origCtx.domain,
      origCtx.documentContent,
      origCtx.extraContext,
      String(feedback),
      origCtx.prevResponse,
    ).catch(e => logger.error({ e, newTaskId }, '[tahp-llm] correction unhandled'))
  })
})
