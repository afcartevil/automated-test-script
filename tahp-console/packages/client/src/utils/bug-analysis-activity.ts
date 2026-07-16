/** 将智能诊断 TaskStream 事件格式化为可读的执行动态 / 任务日志行 */

export interface BugActivityStreamEntry {
  type: string
  payload: Record<string, unknown>
  ts: number
}

const PHASE_LABELS: Record<string, string> = {
  STARTING: '任务启动',
  PREPARING: '准备 Agent',
  CONNECTING_AGENT: '连接 Agent',
  QUEUED: '排队等待',
  FETCH_JIRA_INFO: '拉取 JIRA',
  DOWNLOAD_JIRA_LOGS: '下载日志',
  MATCH_SKILLS: '匹配 Skill',
  ANALYZING: '分析中',
  GENERATING_REPORT: '生成报告',
  COMPLETED: '已完成',
  FAILED: '失败',
  CANCELLED: '已取消',
  WAITING_USER_INPUT: '等待用户输入',
}

const STEP_LABELS: Record<string, string> = {
  'fetch-jira': '拉取 JIRA 工单',
  'download-logs': '下载 JIRA 日志',
  'match-skills': '匹配分析 Skill',
  analyze: '根因分析',
  'generate-report': '生成报告',
}

function formatTs(ts: number): string {
  const d = new Date(ts)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

export function formatBugActivityLine(ev: BugActivityStreamEntry): string | null {
  const p = ev.payload || {}
  const ts = formatTs(ev.ts)

  switch (ev.type) {
    case 'task.started':
      return `[${ts}] 任务已启动${p.jira_key ? ` · ${String(p.jira_key)}` : ''}`
    case 'task.continue_started':
      return `[${ts}] 继续补充分析（第 ${String(p.round || '?')} 轮）`
    case 'task.phase': {
      const phase = String(p.phase || '')
      const label = PHASE_LABELS[phase] || phase
      const msg = typeof p.message === 'string' && p.message.trim() ? ` — ${p.message.trim()}` : ''
      return `[${ts}] 阶段：${label}${msg}`
    }
    case 'task.step': {
      const sid = String(p.step_id || '')
      const label = STEP_LABELS[sid] || sid
      const st = String(p.status || 'running')
      const msg = typeof p.message === 'string' && p.message.trim() ? ` — ${p.message.trim()}` : ''
      return `[${ts}] 步骤 ${label}（${st}）${msg}`
    }
    case 'task.stage_detail': {
      const sid = String(p.step_id || '')
      const label = STEP_LABELS[sid] || sid
      const msg = typeof p.message === 'string' && p.message.trim() ? p.message.trim() : ''
      const skill = typeof p.skill_used === 'string' && p.skill_used ? ` · ${p.skill_used}` : ''
      return `[${ts}] ${label}${skill}${msg ? ` — ${msg}` : ''}`
    }
    case 'task.skill_use': {
      const skill = String(p.skill_id || 'tool')
      const msg = typeof p.message === 'string' && p.message.trim()
        ? p.message.trim()
        : typeof p.args === 'string' && p.args.trim()
          ? p.args.trim()
          : ''
      return `[${ts}] ▶ 调用 ${skill}${msg ? ` — ${msg}` : ''}`
    }
    case 'task.tool_completed': {
      const skill = String(p.skill_id || 'tool')
      const ok = p.error !== true
      return `[${ts}] ${ok ? '✓' : '✗'} 完成 ${skill}`
    }
    case 'task.message':
      if (p.level === 'activity' && typeof p.text === 'string' && p.text.trim()) {
        return `[${ts}] ${p.text.trim()}`
      }
      return null
    case 'task.completed':
      return `[${ts}] 分析完成${typeof p.message === 'string' && p.message ? ` — ${p.message}` : ''}`
    case 'task.failed':
      return `[${ts}] 失败：${String(p.message || p.error || '未知错误')}`
    case 'task.cancelled':
      return `[${ts}] 已取消：${String(p.message || p.error || '')}`
    case 'task.approval_requested':
      return `[${ts}] 等待命令确认：${String(p.command || '').slice(0, 120)}`
    case 'task.user_input_requested':
      return `[${ts}] 等待用户补充配置`
    default:
      return null
  }
}

const ACTIVITY_EVENT_TYPES = new Set([
  'task.started', 'task.continue_started', 'task.phase', 'task.step', 'task.stage_detail',
  'task.skill_use', 'task.tool_completed', 'task.completed', 'task.failed', 'task.cancelled',
  'task.approval_requested', 'task.user_input_requested', 'task.message',
])

export function buildBugActivityLog(stream: BugActivityStreamEntry[]): string {
  const lines: string[] = []
  for (const ev of stream) {
    if (!ACTIVITY_EVENT_TYPES.has(ev.type)) continue
    const line = formatBugActivityLine(ev)
    if (line) lines.push(line)
  }
  return lines.join('\n')
}

export function lastBugActivityHint(stream: BugActivityStreamEntry[]): string | null {
  for (let i = stream.length - 1; i >= 0; i -= 1) {
    const line = formatBugActivityLine(stream[i])
    if (line) return line.replace(/^\[\d{2}:\d{2}:\d{2}\]\s*/, '')
  }
  return null
}
