/**
 * 评测集导入 / 导出（脱敏包）。
 *
 * 评测集默认含真实 JIRA / 日志路径，不能直接进 git。
 * 导出时默认 redact；导入校验 format + suite + case 结构。
 */
import { listEvalCases, readEvalCase, saveEvalCase, isSafeEvalId } from './store'
import { isEvalSuite, type EvalCase, type EvalCaseSource, type EvalSuite, type Rubric } from './types'

export const EVAL_BUNDLE_FORMAT = 'tahp-eval-bundle-v1'
export const EVAL_BUNDLE_VERSION = 1

export interface EvalBundle {
  format: typeof EVAL_BUNDLE_FORMAT
  version: number
  suite: EvalSuite
  exported_at: string
  redacted: boolean
  cases: EvalCase[]
  /** 脱敏时改写过的字段路径，便于人工复核 */
  redaction_notes?: string[]
}

export interface ExportEvalBundleOptions {
  caseIds?: string[]
  /** 默认 true：导出前脱敏 */
  redact?: boolean
}

export interface ImportEvalBundleOptions {
  /** 覆盖已存在同 id 用例；默认 false 跳过 */
  overwrite?: boolean
  /** 强制写入的 suite（须与 bundle.suite 一致，除非空 bundle） */
  suite?: EvalSuite
}

const ABS_PATH_RE = /(?:[A-Za-z]:\\|\\\\|\/(?:home|Users|var|tmp|data|mnt|opt)\/)[^\s"'<>|]*/g
const EMAIL_RE = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g
const JIRA_RE = /\b([A-Z][A-Z0-9]+)-\d+\b/g

function redactText(raw: string | undefined, notes: string[], field: string): string | undefined {
  if (raw == null || raw === '') return raw
  let next = raw
  const before = next
  next = next.replace(ABS_PATH_RE, '[REDACTED_PATH]')
  next = next.replace(EMAIL_RE, '[REDACTED_EMAIL]')
  next = next.replace(JIRA_RE, '$1-[REDACTED]')
  if (next !== before) notes.push(field)
  return next
}

function redactPath(raw: string | undefined, notes: string[], field: string): string | undefined {
  if (raw == null || raw === '') return raw
  notes.push(field)
  const base = raw.replace(/\\/g, '/').split('/').filter(Boolean).pop()
  return base ? `[REDACTED_DIR]/${base}` : '[REDACTED_PATH]'
}

function redactJiraKey(raw: string | undefined, notes: string[]): string | undefined {
  if (!raw) return raw
  notes.push('source.jira_key')
  const m = raw.match(/^([A-Z][A-Z0-9]+)-\d+$/i)
  return m ? `${m[1].toUpperCase()}-[REDACTED]` : '[REDACTED_JIRA]'
}

function redactFormData(
  form: Record<string, string> | undefined,
  notes: string[],
): Record<string, string> | undefined {
  if (!form) return form
  const out: Record<string, string> = {}
  for (const [k, v] of Object.entries(form)) {
    out[k] = redactText(String(v), notes, `source.form_data.${k}`) || ''
  }
  return out
}

/** 单例脱敏（不改动 id / rubric / expected_* 结构化期望） */
export function redactEvalCase(evalCase: EvalCase): { case: EvalCase; notes: string[] } {
  const notes: string[] = []
  const src = evalCase.source || ({ type: 'local' } as EvalCaseSource)
  const source: EvalCaseSource = {
    ...src,
    jira_key: redactJiraKey(src.jira_key, notes),
    log_path: redactPath(src.log_path, notes, 'source.log_path'),
    problem_description: redactText(src.problem_description, notes, 'source.problem_description'),
    query: redactText(src.query, notes, 'source.query'),
    user_notes: redactText(src.user_notes, notes, 'source.user_notes'),
    form_data: redactFormData(src.form_data, notes),
    workspace_id: src.workspace_id
      ? (notes.push('source.workspace_id'), '[REDACTED_WORKSPACE]')
      : src.workspace_id,
    origin_task_id: src.origin_task_id
      ? (notes.push('source.origin_task_id'), '[REDACTED_TASK]')
      : src.origin_task_id,
    origin_pipeline_run_id: src.origin_pipeline_run_id
      ? (notes.push('source.origin_pipeline_run_id'), '[REDACTED_PIPELINE]')
      : src.origin_pipeline_run_id,
    frozen_signals: undefined,
  }
  if (src.frozen_signals) notes.push('source.frozen_signals(omitted)')

  return {
    case: {
      ...evalCase,
      title: redactText(evalCase.title, notes, 'title') || evalCase.title,
      source,
      updated_at: new Date().toISOString(),
    },
    notes: Array.from(new Set(notes)),
  }
}

function validateRubric(rubric: unknown): rubric is Rubric[] {
  if (!Array.isArray(rubric) || !rubric.length) return false
  for (const item of rubric) {
    if (!item || typeof item !== 'object') return false
    const r = item as Rubric
    if (!r.id || !r.criterion || !Number.isFinite(Number(r.weight))) return false
  }
  return true
}

export function validateEvalBundle(raw: unknown): { ok: true; bundle: EvalBundle } | { ok: false; error: string } {
  if (!raw || typeof raw !== 'object') return { ok: false, error: 'bundle 必须是对象' }
  const obj = raw as Record<string, unknown>
  if (obj.format !== EVAL_BUNDLE_FORMAT) {
    return { ok: false, error: `不支持的 format: ${String(obj.format)}（期望 ${EVAL_BUNDLE_FORMAT}）` }
  }
  if (!isEvalSuite(obj.suite)) {
    return { ok: false, error: `非法 suite: ${String(obj.suite)}` }
  }
  if (!Array.isArray(obj.cases) || !obj.cases.length) {
    return { ok: false, error: 'bundle.cases 不能为空' }
  }

  const cases: EvalCase[] = []
  for (const item of obj.cases) {
    if (!item || typeof item !== 'object') return { ok: false, error: 'case 必须是对象' }
    const c = item as EvalCase
    if (!c.id || !isSafeEvalId(c.id)) return { ok: false, error: `非法 case id: ${String(c.id)}` }
    if (!c.source || typeof c.source !== 'object' || !c.source.type) {
      return { ok: false, error: `case ${c.id} 缺少 source.type` }
    }
    if (!validateRubric(c.rubric)) return { ok: false, error: `case ${c.id} rubric 非法` }
    cases.push({
      ...c,
      suite: obj.suite,
      created_at: c.created_at || new Date().toISOString(),
    })
  }

  return {
    ok: true,
    bundle: {
      format: EVAL_BUNDLE_FORMAT,
      version: Number(obj.version) || EVAL_BUNDLE_VERSION,
      suite: obj.suite,
      exported_at: String(obj.exported_at || new Date().toISOString()),
      redacted: obj.redacted !== false,
      cases,
      redaction_notes: Array.isArray(obj.redaction_notes)
        ? obj.redaction_notes.map(String)
        : undefined,
    },
  }
}

export function exportEvalBundle(
  suite: EvalSuite,
  opts: ExportEvalBundleOptions = {},
): { ok: true; bundle: EvalBundle } | { ok: false; error: string } {
  const all = listEvalCases(suite)
  let wanted: EvalCase[]
  if (opts.caseIds?.length) {
    wanted = []
    for (const id of opts.caseIds) {
      const found = readEvalCase(id, suite)
      if (!found) return { ok: false, error: `找不到用例 ${id}` }
      wanted.push(found)
    }
  } else {
    wanted = all
  }

  if (!wanted.length) return { ok: false, error: '评测集为空，无法导出' }

  const redact = opts.redact !== false
  const notes: string[] = []
  const cases = wanted.map(c => {
    if (!redact) return { ...c, suite }
    const { case: next, notes: n } = redactEvalCase(c)
    for (const item of n) notes.push(`${c.id}.${item}`)
    return { ...next, suite }
  })

  return {
    ok: true,
    bundle: {
      format: EVAL_BUNDLE_FORMAT,
      version: EVAL_BUNDLE_VERSION,
      suite,
      exported_at: new Date().toISOString(),
      redacted: redact,
      cases,
      redaction_notes: notes.length ? notes : undefined,
    },
  }
}

export function importEvalBundle(
  raw: unknown,
  opts: ImportEvalBundleOptions = {},
): {
  ok: boolean
  suite?: EvalSuite
  imported: string[]
  skipped: string[]
  overwritten: string[]
  error?: string
} {
  const validated = validateEvalBundle(raw)
  if (!validated.ok) {
    return { ok: false, imported: [], skipped: [], overwritten: [], error: validated.error }
  }
  const { bundle } = validated
  if (opts.suite && opts.suite !== bundle.suite) {
    return {
      ok: false,
      imported: [],
      skipped: [],
      overwritten: [],
      error: `suite 不匹配：bundle=${bundle.suite}，当前=${opts.suite}`,
    }
  }

  const imported: string[] = []
  const skipped: string[] = []
  const overwritten: string[] = []
  const overwrite = opts.overwrite === true

  for (const evalCase of bundle.cases) {
    const existing = readEvalCase(evalCase.id, bundle.suite)
    if (existing && !overwrite) {
      skipped.push(evalCase.id)
      continue
    }
    saveEvalCase(
      {
        ...evalCase,
        suite: bundle.suite,
        updated_at: new Date().toISOString(),
      },
      bundle.suite,
    )
    if (existing) overwritten.push(evalCase.id)
    else imported.push(evalCase.id)
  }

  return { ok: true, suite: bundle.suite, imported, skipped, overwritten }
}
