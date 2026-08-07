/**
 * 适配客观判分 —— 不依赖 LLM，用确定性信号打分。
 *
 * 信号优先级（设计文档）：
 *   pipeline passed ≫ build pass + selfcheck success ≫ adapt completed + 有改动 ≫ soft LLM
 */
import { aggregateScore } from './judge'
import type {
  AdaptObjectiveSignals,
  CaseScore,
  EvalCase,
  JudgeVerdict,
  Rubric,
  RubricVerdict,
} from './types'

/** 客观打分口径版本 —— 变体指纹的一部分 */
export const ADAPT_OBJECTIVE_VERSION = 'adapt-obj-v1'

export const DEFAULT_ADAPT_AGENT_RUBRIC: Rubric[] = [
  {
    id: 'adapt_completed',
    weight: 3,
    must: true,
    scoring: 'objective',
    criterion: '适配 Agent 任务成功完成（status=completed）',
  },
  {
    id: 'has_changes',
    weight: 2,
    must: true,
    scoring: 'objective',
    criterion: '产生了至少一个文件变更（files_modified / file_changes）',
  },
  {
    id: 'skill_hit',
    weight: 1,
    scoring: 'objective',
    criterion: '实际使用的 skill 与期望 related_skills 有交集',
  },
]

export const DEFAULT_ADAPT_PIPELINE_RUBRIC: Rubric[] = [
  {
    id: 'adapt_completed',
    weight: 2,
    must: true,
    scoring: 'objective',
    criterion: '适配阶段完成且有文件变更',
  },
  {
    id: 'build_pass',
    weight: 3,
    must: true,
    scoring: 'objective',
    criterion: '编译阶段通过且产出产物路径',
  },
  {
    id: 'selfcheck_pass',
    weight: 3,
    must: true,
    scoring: 'objective',
    criterion: '自检全部通过（failed=0）',
  },
  {
    id: 'pipeline_passed',
    weight: 1,
    scoring: 'objective',
    criterion: '整条流水线最终状态为 passed',
  },
]

function verdict(
  id: string,
  pass: boolean,
  score: number,
  reason: string,
  evidence?: string,
): RubricVerdict {
  return { id, pass, score, reason, evidence }
}

function scoreAdaptCompleted(signals: AdaptObjectiveSignals): RubricVerdict {
  const pass = signals.adapt_completed === true
  return verdict(
    'adapt_completed',
    pass,
    pass ? 1 : 0,
    pass ? '适配任务已完成' : '适配任务未完成',
    signals.adapt_completed === undefined ? '信号缺失' : `adapt_completed=${signals.adapt_completed}`,
  )
}

function scoreHasChanges(signals: AdaptObjectiveSignals): RubricVerdict {
  const count = signals.files_modified_count ?? 0
  const pass = count > 0
  return verdict(
    'has_changes',
    pass,
    pass ? 1 : 0,
    pass ? `产生了 ${count} 个文件变更` : '没有任何文件变更',
    `files_modified_count=${count}`,
  )
}

function scoreSkillHit(signals: AdaptObjectiveSignals): RubricVerdict {
  const expected = (signals.expected_skills || []).filter(Boolean)
  const used = (signals.skills_used || []).filter(Boolean)
  if (!expected.length) {
    // 未声明期望 skill 时不苛责，给中性通过分
    return verdict('skill_hit', true, 1, '未声明期望 skill，跳过命中检查', 'expected_skills=[]')
  }
  const usedSet = new Set(used.map(s => s.toLowerCase()))
  const hits = expected.filter(s => usedSet.has(s.toLowerCase()))
  const ratio = hits.length / expected.length
  const pass = hits.length > 0
  return verdict(
    'skill_hit',
    pass,
    ratio,
    pass ? `命中 ${hits.length}/${expected.length}: ${hits.join(', ')}` : '未命中任何期望 skill',
    `used=[${used.join(', ')}]`,
  )
}

function scoreBuildPass(signals: AdaptObjectiveSignals): RubricVerdict {
  if (signals.build_pass === null) {
    return verdict('build_pass', true, 1, '本用例不适用编译信号', 'build_pass=null')
  }
  if (signals.build_pass === undefined) {
    return verdict('build_pass', false, 0, '缺少编译信号', 'build_pass=undefined')
  }
  const hasArtifact = signals.build_has_artifact !== false
  const pass = signals.build_pass === true && hasArtifact
  return verdict(
    'build_pass',
    pass,
    pass ? 1 : signals.build_pass ? 0.4 : 0,
    pass
      ? '编译通过且有产物'
      : signals.build_pass
        ? '编译标记通过但缺少产物路径'
        : '编译未通过',
    `build_pass=${signals.build_pass}, has_artifact=${signals.build_has_artifact}`,
  )
}

function scoreSelfcheckPass(signals: AdaptObjectiveSignals): RubricVerdict {
  if (signals.selfcheck_pass === null) {
    return verdict('selfcheck_pass', true, 1, '本用例不适用自检信号', 'selfcheck_pass=null')
  }
  if (signals.selfcheck_pass === undefined) {
    return verdict('selfcheck_pass', false, 0, '缺少自检信号', 'selfcheck_pass=undefined')
  }
  const total = signals.selfcheck_total ?? 0
  const passed = signals.selfcheck_passed ?? 0
  const failed = signals.selfcheck_failed ?? 0
  const pass = signals.selfcheck_pass === true && failed === 0
  const ratio = total > 0 ? passed / total : pass ? 1 : 0
  return verdict(
    'selfcheck_pass',
    pass,
    pass ? 1 : ratio,
    pass
      ? `自检全部通过（${passed}/${total}）`
      : `自检未通过（passed=${passed}, failed=${failed}, total=${total}）`,
    `selfcheck_pass=${signals.selfcheck_pass}`,
  )
}

function scorePipelinePassed(signals: AdaptObjectiveSignals): RubricVerdict {
  if (signals.pipeline_passed === null) {
    return verdict('pipeline_passed', true, 1, '本用例不适用整链信号', 'pipeline_passed=null')
  }
  if (signals.pipeline_passed === undefined) {
    return verdict('pipeline_passed', false, 0, '缺少流水线终态', 'pipeline_passed=undefined')
  }
  const pass = signals.pipeline_passed === true
  return verdict(
    'pipeline_passed',
    pass,
    pass ? 1 : 0,
    pass ? '流水线最终 passed' : '流水线未达到 passed',
    `pipeline_passed=${signals.pipeline_passed}`,
  )
}

const OBJECTIVE_SCORERS: Record<string, (s: AdaptObjectiveSignals) => RubricVerdict> = {
  adapt_completed: scoreAdaptCompleted,
  has_changes: scoreHasChanges,
  skill_hit: scoreSkillHit,
  build_pass: scoreBuildPass,
  selfcheck_pass: scoreSelfcheckPass,
  pipeline_passed: scorePipelinePassed,
}

/**
 * 只对 scoring=objective（或未标但 id 命中客观表）的项打分。
 * 返回的 JudgeVerdict 可与 LLM 项合并后再 aggregateScore。
 */
export function scoreObjectiveRubrics(
  rubric: Rubric[],
  signals: AdaptObjectiveSignals,
): JudgeVerdict {
  const rubrics: RubricVerdict[] = []
  for (const item of rubric) {
    const isObjective = item.scoring === 'objective' || (!item.scoring && item.id in OBJECTIVE_SCORERS)
    if (!isObjective) continue
    const scorer = OBJECTIVE_SCORERS[item.id]
    if (!scorer) {
      rubrics.push(verdict(item.id, false, 0, `未知客观项 ${item.id}`, 'no scorer'))
      continue
    }
    rubrics.push(scorer(signals))
  }
  return { rubrics, summary: '客观信号打分' }
}

/** 整例仅客观项时的便捷入口 */
export function scoreAdaptCase(evalCase: EvalCase, signals: AdaptObjectiveSignals): CaseScore {
  const objective = scoreObjectiveRubrics(evalCase.rubric, signals)
  // 把未覆盖的 llm 项按缺失处理（offline / 无判官时）
  return aggregateScore(objective, evalCase.rubric)
}

/**
 * 合并客观结论与 LLM 结论：客观项以客观为准，其余用 LLM。
 */
export function mergeObjectiveAndLlm(
  rubric: Rubric[],
  signals: AdaptObjectiveSignals,
  llm: JudgeVerdict | null,
): CaseScore {
  const objective = scoreObjectiveRubrics(rubric, signals)
  const byId = new Map<string, RubricVerdict>()
  for (const r of llm?.rubrics || []) byId.set(r.id, r)
  for (const r of objective.rubrics) byId.set(r.id, r) // 客观覆盖同名

  const merged: JudgeVerdict = {
    rubrics: rubric.map(item => {
      const found = byId.get(item.id)
      if (found) return found
      return verdict(item.id, false, 0, '判官未对该项给出结论')
    }),
    summary: [objective.summary, llm?.summary].filter(Boolean).join('；') || undefined,
  }
  return aggregateScore(merged, rubric)
}

/** 从适配报告 JSON 抽取客观信号 */
export function signalsFromAdaptReport(
  report: Record<string, unknown>,
  expectedSkills?: string[],
): AdaptObjectiveSignals {
  const status = String(report.status || '')
  const files =
    (Array.isArray(report.files_modified) ? report.files_modified : null) ||
    (Array.isArray(report.file_changes) ? report.file_changes : null) ||
    (Array.isArray(report.fileChanges) ? report.fileChanges : null) ||
    []

  const skillsRaw =
    (Array.isArray(report.skills_used) ? report.skills_used : null) ||
    (Array.isArray(report.skillsUsed) ? report.skillsUsed : null) ||
    []

  const skills_used = skillsRaw.map((s: unknown) => {
    if (typeof s === 'string') return s
    if (s && typeof s === 'object' && 'skill_id' in (s as object)) {
      return String((s as { skill_id: unknown }).skill_id)
    }
    return String(s)
  }).filter(Boolean)

  return {
    adapt_completed: status === 'completed',
    files_modified_count: files.length,
    skills_used,
    expected_skills: expectedSkills,
    build_pass: null,
    build_has_artifact: null,
    selfcheck_pass: null,
    pipeline_passed: null,
  }
}

/** 从流水线 run 抽取客观信号 */
export function signalsFromPipelineRun(run: {
  status?: string
  domains?: Array<{ status?: string; changed_files?: string[]; related_skills?: string[] }>
  stages?: Record<string, {
    status?: string
    progress?: Record<string, unknown>
    summary?: Record<string, unknown>
  }>
}): AdaptObjectiveSignals {
  const domains = (run.domains || []).filter(d => d)
  const adaptDone = domains.length
    ? domains.every(d => d.status === 'done' || d.status === 'skipped')
    : run.stages?.adapt?.status === 'done'
  const changed = domains.reduce((n, d) => n + (d.changed_files?.length || 0), 0)
  const expected = Array.from(new Set(domains.flatMap(d => d.related_skills || [])))

  const build = run.stages?.build
  const buildProgress = build?.progress || {}
  const buildSummary = build?.summary || {}
  const buildState = String(buildProgress.state || '')
  const hasArtifact = !!(buildSummary.artifacts_dir || buildSummary.pkg_path || buildProgress.artifacts_dir)
  const buildPass =
    build?.status === 'done' && (buildState === 'success' || buildState === '' || hasArtifact)
      ? true
      : build?.status === 'failed' || buildState === 'failed'
        ? false
        : build
          ? buildState === 'success'
          : null

  const selfcheck = run.stages?.selfcheck
  const scProgress = selfcheck?.progress || {}
  const scState = String(scProgress.state || '')
  const scPassed = Number(scProgress.passed ?? 0)
  const scFailed = Number(scProgress.failed ?? 0)
  const scTotal = Number(scProgress.total ?? scPassed + scFailed)
  let selfcheckPass: boolean | null = null
  if (selfcheck) {
    if (scState === 'success' || (selfcheck.status === 'done' && scFailed === 0)) selfcheckPass = true
    else if (scState === 'case_failed' || selfcheck.status === 'failed') selfcheckPass = false
    else if (selfcheck.status === 'done') selfcheckPass = scFailed === 0
    else selfcheckPass = false
  }

  return {
    adapt_completed: !!adaptDone && changed > 0,
    files_modified_count: changed,
    skills_used: expected,
    expected_skills: expected,
    build_pass: build ? (buildPass ?? false) : null,
    build_has_artifact: build ? hasArtifact : null,
    selfcheck_pass: selfcheckPass,
    selfcheck_passed: scPassed,
    selfcheck_failed: scFailed,
    selfcheck_total: scTotal,
    pipeline_passed: run.status === 'passed',
  }
}
