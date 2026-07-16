export type AnalysisPhaseDef = {
  key: string
  label: string
  icon: string
}

export const ANALYSIS_PHASE_DEFS: AnalysisPhaseDef[] = [
  { key: 'fetching', label: '获取提交列表', icon: '🔍' },
  { key: 'format_patch', label: '生成 Patch / Diff', icon: '📦' },
  { key: 'collecting', label: '数据采集', icon: '📥' },
  { key: 'analyzing', label: '脚本评分', icon: '🔧' },
  { key: 'llm_analyzing', label: 'LLM 深度分析', icon: '🤖' },
  { key: 'monthly_recommendation', label: '子 tag 统计', icon: '🏷️' },
  { key: 'summarizing', label: '综合分析', icon: '📝' },
]

const CURRENT_PHASE_META: Record<string, { icon: string; label: string }> = {
  fetching: { icon: '🔍', label: '获取提交列表' },
  format_patch: { icon: '📦', label: '生成 Patch / Diff' },
  collecting: { icon: '📥', label: '数据采集' },
  analyzing: { icon: '🔧', label: '脚本评分' },
  llm_analyzing: { icon: '🤖', label: 'LLM 深度分析' },
  monthly_recommendation: { icon: '🏷️', label: '子 tag 统计' },
  summarizing: { icon: '📝', label: '综合分析' },
  running: { icon: '⏳', label: '分析进行中' },
  pending: { icon: '⏳', label: '等待启动' },
}

export type AnalysisPhaseStep = AnalysisPhaseDef & {
  total: number
  current: number
  percent: number
  status: 'pending' | 'running' | 'done'
}

export type AnalysisLogLine = {
  time?: string
  phase?: string
  msg?: string
  message?: string
}

export type SquashValidationCheck = {
  name: string
  passed: boolean
  detail: string
}

export type SquashValidation = {
  ok: boolean
  summary: string
  checks: SquashValidationCheck[]
  warnings: string[]
}

const SQUASH_CHECK_LABELS: Record<string, string> = {
  file_exists: '文件存在',
  ancestor: '线性区间',
  commit_count: 'Commit 数量',
  git_reference: 'Git 基准',
  read_squash: '读取 squash',
  nonempty: 'Diff 非空',
  file_set: '变更文件集合',
  line_stats: '增删行统计',
  content_match: '正文一致性',
}

export function squashCheckLabel(name: string) {
  return SQUASH_CHECK_LABELS[name] || name
}

export function squashValidationFromProgress(progress: any): SquashValidation | null {
  const raw = progress?.squash_validation
  if (!raw || typeof raw !== 'object') return null
  const checks = Array.isArray(raw.checks)
    ? raw.checks.map((item: any) => ({
        name: String(item?.name || ''),
        passed: Boolean(item?.passed),
        detail: String(item?.detail || ''),
      }))
    : []
  return {
    ok: Boolean(raw.ok),
    summary: String(raw.summary || ''),
    checks,
    warnings: Array.isArray(raw.warnings) ? raw.warnings.map(String) : [],
  }
}

export function currentPhaseMeta(status?: string) {
  const raw = String(status || '').toLowerCase()
  // 死机风险扫描与 LLM 并行，无独立进度条；顶部仍显示 LLM 阶段
  const key = raw === 'defect_scan' ? 'llm_analyzing' : raw
  return CURRENT_PHASE_META[key] || CURRENT_PHASE_META.running
}

function phaseStepStatus(
  phaseKey: string,
  snapshot: { done?: boolean; total?: number; current?: number },
  currentStatus: string,
) {
  if (snapshot.done) return 'done' as const
  const total = Number(snapshot.total) || 0
  const current = Number(snapshot.current) || 0
  if (currentStatus === phaseKey) return 'running' as const
  if (current > 0 && total > 0 && current < total) return 'running' as const
  return 'pending' as const
}

export function buildAnalysisPhaseSteps(progress: any): AnalysisPhaseStep[] {
  const phases = Array.isArray(progress?.phases) ? progress.phases : []
  const phaseMap = new Map<string, any>()
  for (const item of phases) {
    if (item?.key) phaseMap.set(String(item.key), item)
  }

  const currentStatus = String(progress?.status || '').toLowerCase()
  const steps: AnalysisPhaseStep[] = []

  for (const def of ANALYSIS_PHASE_DEFS) {
    const snapshot = phaseMap.get(def.key)
    if (!snapshot) continue
    const total = Number(snapshot.total) || 0
    const current = Math.min(Number(snapshot.current) || 0, total > 0 ? total : 0)
    const percent = total > 0 ? Math.min(100, Math.floor((current / total) * 100)) : 0
    steps.push({
      ...def,
      total,
      current,
      percent,
      status: phaseStepStatus(def.key, snapshot, currentStatus),
    })
  }

  return steps
}

export function analysisProgressLogs(progress: any): AnalysisLogLine[] {
  const log = progress?.log
  return Array.isArray(log) ? log : []
}

export function analysisLogText(line: AnalysisLogLine) {
  return line.msg || line.message || ''
}
