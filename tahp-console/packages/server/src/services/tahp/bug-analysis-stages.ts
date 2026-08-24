/**
 * 智能诊断 — Agent 结构化阶段标记解析与 BFF 阶段映射
 */

export const BUG_STAGE_MARKER_IDS = [
  'fetch_jira',
  'download_logs',
  'match_skills',
  'analyze',
  'generate_report',
] as const

export type BugStageMarkerId = typeof BUG_STAGE_MARKER_IDS[number]

/** BFF 内部 phase（与前端进度条对齐） */
export const BUG_UI_PHASES = {
  FETCH_JIRA_INFO: 'FETCH_JIRA_INFO',
  DOWNLOAD_JIRA_LOGS: 'DOWNLOAD_JIRA_LOGS',
  MATCH_SKILLS: 'MATCH_SKILLS',
  ANALYZING: 'ANALYZING',
  GENERATING_REPORT: 'GENERATING_REPORT',
} as const

export type BugUiPhase = typeof BUG_UI_PHASES[keyof typeof BUG_UI_PHASES]

export const BUG_UI_PHASE_ORDER: BugUiPhase[] = [
  BUG_UI_PHASES.FETCH_JIRA_INFO,
  BUG_UI_PHASES.DOWNLOAD_JIRA_LOGS,
  BUG_UI_PHASES.MATCH_SKILLS,
  BUG_UI_PHASES.ANALYZING,
  BUG_UI_PHASES.GENERATING_REPORT,
]

export const BUG_UI_PHASE_PROGRESS: Record<BugUiPhase, number> = {
  [BUG_UI_PHASES.FETCH_JIRA_INFO]: 15,
  [BUG_UI_PHASES.DOWNLOAD_JIRA_LOGS]: 32,
  [BUG_UI_PHASES.MATCH_SKILLS]: 48,
  [BUG_UI_PHASES.ANALYZING]: 72,
  [BUG_UI_PHASES.GENERATING_REPORT]: 92,
}

export const BUG_MARKER_TO_PHASE: Record<BugStageMarkerId, BugUiPhase> = {
  fetch_jira: BUG_UI_PHASES.FETCH_JIRA_INFO,
  download_logs: BUG_UI_PHASES.DOWNLOAD_JIRA_LOGS,
  match_skills: BUG_UI_PHASES.MATCH_SKILLS,
  analyze: BUG_UI_PHASES.ANALYZING,
  generate_report: BUG_UI_PHASES.GENERATING_REPORT,
}

export const BUG_MARKER_TO_STEP_ID: Record<BugStageMarkerId, string> = {
  fetch_jira: 'fetch-jira',
  download_logs: 'download-logs',
  match_skills: 'match-skills',
  analyze: 'analyze',
  generate_report: 'generate-report',
}

export interface ParsedBugStageMarker {
  markerId: BugStageMarkerId
  phase: BugUiPhase
  stepId: string
  status: 'running' | 'success' | 'failed'
  fields: Record<string, string>
  rawBlock: string
  startIndex: number
}

const STAGE_BLOCK_RE = /=== TAHP_STAGE:(fetch_jira|download_logs|match_skills|analyze|generate_report) ===\r?\n([\s\S]*?)=== END_TAHP_STAGE ===/g

function parseStageFields(body: string): Record<string, string> {
  const fields: Record<string, string> = {}
  for (const line of body.split(/\r?\n/)) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('#')) continue
    const idx = trimmed.indexOf(':')
    if (idx <= 0) continue
    const key = trimmed.slice(0, idx).trim().toLowerCase()
    const value = trimmed.slice(idx + 1).trim()
    if (key) fields[key] = value
  }
  return fields
}

function normalizeStageStatus(raw?: string): 'running' | 'success' | 'failed' {
  const s = String(raw || '').toLowerCase()
  if (s === 'failed' || s === 'error' || s === 'fail') return 'failed'
  if (s === 'running' || s === 'in_progress' || s === 'progress') return 'running'
  return 'success'
}

export function findBugStageMarkers(text: string, fromIndex = 0): ParsedBugStageMarker[] {
  const hits: ParsedBugStageMarker[] = []
  STAGE_BLOCK_RE.lastIndex = 0
  let m: RegExpExecArray | null
  while ((m = STAGE_BLOCK_RE.exec(text)) !== null) {
    if (m.index < fromIndex) continue
    const markerId = m[1] as BugStageMarkerId
    const fields = parseStageFields(m[2])
    hits.push({
      markerId,
      phase: BUG_MARKER_TO_PHASE[markerId],
      stepId: BUG_MARKER_TO_STEP_ID[markerId],
      status: normalizeStageStatus(fields.status),
      fields,
      rawBlock: m[0],
      startIndex: m.index,
    })
  }
  return hits
}

/** 将 Agent 阶段字段转为 UI 可展示的详情行 */
export function formatStageDetailLines(markerId: BugStageMarkerId, fields: Record<string, string>): string[] {
  const lines: string[] = []
  const push = (label: string, key: string) => {
    const v = fields[key]
    if (v) lines.push(`${label}: ${v}`)
  }

  push('说明', 'message')
  push('使用 Skill', 'skill_used')

  if (markerId === 'fetch_jira') {
    push('JIRA Key', 'jira_key')
    push('拉取成功', 'fetch_ok')
    push('Issue 标题', 'issue_summary')
    push('状态', 'status')
    push('优先级', 'priority')
    push('经办', 'assignee')
    push('报告人', 'reporter')
    push('描述摘要', 'description_preview')
    push('评论数', 'comment_count')
    push('附件数', 'attachment_count')
  } else if (markerId === 'download_logs') {
    push('日志已下载', 'logs_downloaded')
    push('日志路径', 'log_paths')
    push('附件数', 'attachment_count')
  } else if (markerId === 'match_skills') {
    push('已匹配', 'skills_matched')
    push('Skill 清单', 'matched_skills')
    push('未匹配原因', 'match_note')
  } else if (markerId === 'analyze') {
    push('分析已开始', 'analysis_started')
    push('所用 Skill', 'matched_skills')
  } else if (markerId === 'generate_report') {
    push('报告就绪', 'report_ready')
  }

  return lines
}

/** 从流式正文中移除阶段标记块（避免在「AI 分析」面板重复展示） */
export function stripBugStageMarkers(text: string): string {
  STAGE_BLOCK_RE.lastIndex = 0
  return text.replace(STAGE_BLOCK_RE, '').trim()
}

const TOOLS_INVOKED_RE = /=== TOOLS_INVOKED ===[\s\S]*?(?:=== END ===\s*)?$/g
/** 8 节报告首段标题（与 Agent 提示词一致，兼容 # / ## / ###） */
const REPORT_SECTION1_RE = /(?:^|\n)(#{1,4}\s*1\.\s*(?:摘要|TL;DR)[^\n]*)/i

/**
 * 从 Agent 完整输出中提取 Step 5 的 8 节分析报告正文（去掉阶段标记、过程叙述与 TOOLS_INVOKED）。
 */
export function extractBugAnalysisReportBody(text: string): string {
  if (!text?.trim()) return ''
  let body = stripBugStageMarkers(text)
  body = body.replace(TOOLS_INVOKED_RE, '').trim()
  const m = REPORT_SECTION1_RE.exec(body)
  if (m) {
    const start = m.index + (m[0].startsWith('\n') ? 1 : 0)
    return body.slice(start).trim()
  }
  return body
}

/** 无报告正文时的最小有效输出长度（P0 完成门禁） */
export const MIN_MEANINGFUL_CHARS = 200
/** `llm_response` 落盘上限（P0 失败报告截断；P1 成功路径共用） */
export const LLM_RESPONSE_MAX_BYTES = 65536

export type RunFailureReason = 'empty_response' | 'spin_detected'

export type RunOutcome =
  | { ok: true }
  | { ok: false; failureReason: 'empty_response'; message: string }

export class BugAnalysisEmptyResultError extends Error {
  readonly failureReason: 'empty_response' = 'empty_response'
  constructor(message: string) {
    super(message)
    this.name = 'BugAnalysisEmptyResultError'
  }
}

export function evaluateRunOutcome(fullResponse: string, toolCallCount: number): RunOutcome {
  const produced = fullResponse.trim().length
  const bodyLen = extractBugAnalysisReportBody(fullResponse).trim().length
  if (produced === 0 && toolCallCount === 0) {
    return {
      ok: false,
      failureReason: 'empty_response',
      message: 'Agent 空返回（0 工具调用 / 0 字符输出）',
    }
  }
  if (bodyLen === 0 && produced < MIN_MEANINGFUL_CHARS && toolCallCount === 0) {
    return {
      ok: false,
      failureReason: 'empty_response',
      message: `Agent 输出过短且无报告正文（${produced} 字符）`,
    }
  }
  return { ok: true }
}

/** 按 UTF-8 字节截断，避免劈开多字节字符 */
export function truncateForReport(text: string, maxBytes = LLM_RESPONSE_MAX_BYTES): string {
  if (!text) return ''
  const buf = Buffer.from(text, 'utf8')
  if (buf.length <= maxBytes) return text
  let end = maxBytes
  while (end > 0 && (buf[end] & 0xc0) === 0x80) end -= 1
  return `${buf.subarray(0, end).toString('utf8')}\n\n[... 已截断]`
}
