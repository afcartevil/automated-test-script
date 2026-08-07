/**
 * 评测用例冷启动 —— 从已有 Bug 分析报告转存。
 *
 * 带 corrections 的历史任务优先：有补充轮次说明首轮没达标，是天然负样本。
 */
import { listBugReports, readBugReport } from '../bug-analysis'
import { listEvalCases, readEvalCase, saveEvalCase } from './store'
import type { EvalCase, Rubric } from './types'

/** 转存时预置的评分骨架，criterion 需要人工按具体问题改写 */
export const DEFAULT_RUBRIC: Rubric[] = [
  {
    id: 'root_cause',
    weight: 3,
    must: true,
    criterion: '明确指出根因，且与该问题的实际修复方向一致（此处请改写为本例的具体根因）',
  },
  {
    id: 'evidence',
    weight: 2,
    must: true,
    criterion: '结论有可追溯依据（引用 log 时间戳 / 关键字 / 代码位置），未编造 API、寄存器或字段名',
  },
  {
    id: 'actionable',
    weight: 1,
    criterion: '给出可执行的下一步验证或修复动作，而非泛泛的排查建议',
  },
  {
    id: 'skill_choice',
    weight: 1,
    criterion: '选用了与问题域匹配的分析 skill（此处请填写本例期望的 skill）',
  },
]

interface BugReportShape {
  task_id?: string
  jira_key?: string
  title?: string
  status?: string
  analysis_mode?: string
  local_log_path?: string
  user_description?: string
  corrections?: unknown
  skills_used?: unknown
  started_at?: string
}

export interface EvalCaseCandidate {
  task_id: string
  jira_key?: string
  title?: string
  analysis_mode?: string
  started_at?: string
  corrections_count: number
  /** 已经转存过的用例 id */
  existing_case_id?: string
}

function sanitizeIdPart(raw: string): string {
  return raw.replace(/[^A-Za-z0-9._-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60)
}

function uniqueCaseId(base: string): string {
  const taken = new Set(listEvalCases('bug-analysis').map(c => c.id))
  if (!taken.has(base)) return base
  for (let i = 2; i < 100; i++) {
    const next = `${base}-${i}`
    if (!taken.has(next)) return next
  }
  return `${base}-${Date.now()}`
}

function correctionsCount(report: BugReportShape): number {
  return Array.isArray(report.corrections) ? report.corrections.length : 0
}

/**
 * 可转存为评测用例的历史报告。带补充轮次的排前面。
 */
export function listEvalCaseCandidates(limit = 100): EvalCaseCandidate[] {
  const summaries = listBugReports() as Array<{ task_id?: string }>
  const originIndex = new Map<string, string>()
  for (const c of listEvalCases('bug-analysis')) {
    if (c.source.origin_task_id) originIndex.set(c.source.origin_task_id, c.id)
  }

  const candidates: EvalCaseCandidate[] = []
  for (const summary of summaries.slice(0, limit)) {
    const taskId = summary.task_id
    if (!taskId) continue
    const report = readBugReport(taskId) as BugReportShape | null
    if (!report || report.status !== 'completed') continue
    candidates.push({
      task_id: taskId,
      jira_key: report.jira_key,
      title: report.title,
      analysis_mode: report.analysis_mode,
      started_at: report.started_at,
      corrections_count: correctionsCount(report),
      existing_case_id: originIndex.get(taskId),
    })
  }

  return candidates.sort((a, b) => {
    if (a.corrections_count !== b.corrections_count) return b.corrections_count - a.corrections_count
    return String(b.started_at || '').localeCompare(String(a.started_at || ''))
  })
}

export interface CreateCaseFromReportOptions {
  caseId?: string
  rubric?: Rubric[]
  labels?: string[]
}

export function createEvalCaseFromReport(
  taskId: string,
  opts: CreateCaseFromReportOptions = {},
): { ok: boolean; evalCase?: EvalCase; error?: string } {
  const report = readBugReport(taskId) as BugReportShape | null
  if (!report) return { ok: false, error: `找不到报告 ${taskId}` }

  const isLocal = report.analysis_mode === 'local'
  const logPath = report.local_log_path?.trim()
  if (isLocal && !logPath) {
    return { ok: false, error: '本地日志报告缺少 local_log_path，无法复现' }
  }
  const jiraKey = report.jira_key?.trim()
  if (!isLocal && (!jiraKey || jiraKey.startsWith('LOCAL-'))) {
    return { ok: false, error: '报告缺少有效 JIRA Key，无法复现' }
  }

  const baseId = sanitizeIdPart(opts.caseId || `eval-${isLocal ? taskId : jiraKey}`)
  if (!baseId) return { ok: false, error: '无法生成合法的用例 ID' }
  const caseId = opts.caseId ? baseId : uniqueCaseId(baseId)
  if (opts.caseId && readEvalCase(caseId, 'bug-analysis')) {
    return { ok: false, error: `用例 ${caseId} 已存在` }
  }

  const evalCase: EvalCase = {
    id: caseId,
    suite: 'bug-analysis',
    title: report.title || jiraKey || taskId,
    source: {
      type: isLocal ? 'local' : 'jira',
      jira_key: isLocal ? undefined : jiraKey,
      log_path: isLocal ? logPath : undefined,
      problem_description: report.user_description?.trim() || undefined,
      origin_task_id: taskId,
    },
    rubric: opts.rubric?.length ? opts.rubric : DEFAULT_RUBRIC.map(r => ({ ...r })),
    labels: opts.labels,
    created_at: new Date().toISOString(),
    had_corrections: correctionsCount(report) > 0,
  }

  if (evalCase.source.type === 'local' && !evalCase.source.problem_description) {
    return { ok: false, error: '本地日志用例缺少问题描述，无法复现' }
  }

  saveEvalCase(evalCase, 'bug-analysis')
  return { ok: true, evalCase }
}
