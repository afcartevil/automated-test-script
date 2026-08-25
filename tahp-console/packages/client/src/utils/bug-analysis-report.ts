/**
 * 智能诊断 — 报告提取与历史阶段解析（与 server bug-analysis-stages 保持一致）
 */

const STAGE_BLOCK_RE = /=== TAHP_STAGE:(fetch_jira|download_logs|match_skills|analyze|generate_report) ===\r?\n([\s\S]*?)=== END_TAHP_STAGE ===/g
const TOOLS_INVOKED_RE = /=== TOOLS_INVOKED ===[\s\S]*?(?:=== END ===\s*)?$/g
const REPORT_SECTION1_RE = /(?:^|\n)(#{1,4}\s*1\.\s*(?:摘要|TL;DR)[^\n]*)/i

const STEP_BY_MARKER: Record<string, string> = {
  fetch_jira: 'fetch-jira',
  download_logs: 'download-logs',
  match_skills: 'match-skills',
  analyze: 'analyze',
  generate_report: 'generate-report',
}

export interface HistoryStageDetail {
  stage_id: string
  step_id: string
  status: 'running' | 'success' | 'failed'
  message?: string
  detail_lines?: string[]
  fields?: Record<string, string>
}

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

function formatDetailLines(markerId: string, fields: Record<string, string>): string[] {
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

export function stripBugStageMarkers(text: string): string {
  STAGE_BLOCK_RE.lastIndex = 0
  return text.replace(STAGE_BLOCK_RE, '').trim()
}

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

/** 从落盘 llm_response 还原 Agent 进度步骤详情（历史任务只读展示） */
export function parseHistoryStageDetails(text: string): Record<string, HistoryStageDetail> {
  const result: Record<string, HistoryStageDetail> = {}
  if (!text?.trim()) return result
  STAGE_BLOCK_RE.lastIndex = 0
  let m: RegExpExecArray | null
  while ((m = STAGE_BLOCK_RE.exec(text)) !== null) {
    const markerId = m[1]
    const stepId = STEP_BY_MARKER[markerId]
    if (!stepId) continue
    const fields = parseStageFields(m[2])
    const statusRaw = String(fields.status || '').toLowerCase()
    const status: HistoryStageDetail['status'] = statusRaw === 'failed' || statusRaw === 'error'
      ? 'failed'
      : statusRaw === 'running' || statusRaw === 'in_progress'
        ? 'running'
        : 'success'
    result[stepId] = {
      stage_id: markerId,
      step_id: stepId,
      status,
      message: fields.message,
      detail_lines: formatDetailLines(markerId, fields),
      fields,
    }
  }
  return result
}

export function reportToBugTask(report: {
  task_id: string
  jira_key: string
  jira_url: string
  module?: string
  title?: string
  status: string
  started_at: string
  completed_at?: string
  duration_ms?: number
  skills_used?: string[]
  skills_improved?: import('@/api/tahp/bug-analysis').SkillImproveRecord[]
  error?: string
  llm_response?: string
  user_description?: string
  extra_context?: string
  corrections?: string[]
  analysis_mode?: string
  local_log_path?: string
}): import('@/api/tahp/bug-analysis').BugTask {
  const failed = report.status === 'failed'
  return {
    task_id: report.task_id,
    jira_key: report.jira_key,
    jira_url: report.jira_url,
    module: report.module as import('@/api/tahp/bug-analysis').BugTask['module'],
    status: failed ? 'failed' : 'completed',
    phase: failed ? 'FAILED' : 'COMPLETED',
    progress: failed ? undefined : 100,
    started_at: report.started_at,
    completed_at: report.completed_at,
    skills_used: report.skills_used,
    skills_improved: report.skills_improved,
    title: report.title,
    error: report.error,
    llm_response: report.llm_response,
    user_description: report.user_description,
    extra_context: report.extra_context,
    corrections: report.corrections,
    analysis_mode: report.analysis_mode as import('@/api/tahp/bug-analysis').BugTask['analysis_mode'],
    local_log_path: report.local_log_path,
  }
}

export interface ReportSectionBlock {
  id: string
  title: string
  heading: string
  content: string
  defaultSelected: boolean
}

export function isJiraRemarkTitle(title: string): boolean {
  return /Jira\s*备注/i.test(title)
}

export function isRootCauseTitle(title: string): boolean {
  return /根因定位/.test(title)
}

export function isDefaultJiraCommentSection(title: string): boolean {
  return isRootCauseTitle(title) || isJiraRemarkTitle(title)
}

const SECTION_HEADING_RE = /^#{1,4}\s+\d+\.\s+/
const SECTION_TITLE_RE = /^#{1,4}\s+\d+\.\s+(.+)$/

/** 按报告中的编号标题（### 1. xxx）拆分为可选块 */
export function splitReportIntoSections(reportMarkdown: string): ReportSectionBlock[] {
  if (!reportMarkdown?.trim()) return []
  const lines = reportMarkdown.split(/\r?\n/)
  const blocks: ReportSectionBlock[] = []
  let current: ReportSectionBlock | null = null

  for (const line of lines) {
    if (SECTION_HEADING_RE.test(line.trim())) {
      if (current) blocks.push(current)
      const heading = line.trim()
      const m = heading.match(SECTION_TITLE_RE)
      const title = (m?.[1] || heading).trim()
      const id = title.replace(/\s+/g, '-').slice(0, 48) || `section-${blocks.length + 1}`
      current = {
        id,
        title,
        heading,
        content: `${heading}\n`,
        defaultSelected: isDefaultJiraCommentSection(title),
      }
    } else if (current) {
      current.content += `${line}\n`
    }
  }
  if (current) blocks.push(current)
  return blocks
}

export function composeReportSections(
  sections: ReportSectionBlock[],
  selectedIds: string[],
): string {
  const picked = new Set(selectedIds)
  return sections
    .filter(s => picked.has(s.id))
    .map(s => s.content.trim())
    .filter(Boolean)
    .join('\n\n')
    .trim()
}
