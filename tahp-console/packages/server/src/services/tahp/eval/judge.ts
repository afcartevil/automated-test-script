/**
 * LLM-as-judge —— 按用例 rubric 给 Bug 分析报告打分。
 *
 * 分层同 gerrit-case-recommend-llm：纯函数（构造 prompt / 解析 / 聚合）与 LLM 调用分离，
 * 测试只测纯函数，不打网络。
 */
import { safeParseLLMJSON } from '../../../lib/llm-json'
import { callTahpLLM } from '../llm-caller'
import type { CaseScore, EvalCase, JudgeVerdict, Rubric, RubricVerdict } from './types'

/** judge prompt 版本 —— 变体指纹的一部分，改判分口径时必须同步递增 */
export const JUDGE_PROMPT_VERSION = 'v1'

/** 加权总分达此值判 pass */
export const PASS_THRESHOLD = 0.8
/** 加权总分达此值判 warn，低于则 fail */
export const WARN_THRESHOLD = 0.6

const JUDGE_MAX_TOKENS = 4096

// ─── 纯函数：构造 prompt ─────────────────────────────────────────────────────

export function buildJudgePrompt(
  evalCase: EvalCase,
  reportBody: string,
): { instructions: string; userMessage: string } {
  const rubricLines = evalCase.rubric
    .map(r => `- id=${r.id} | weight=${r.weight}${r.must ? ' | 必过项' : ''} | ${r.criterion}`)
    .join('\n')

  const instructions = `你是 TAHP 平台的诊断报告评审员，负责按给定评分标准客观评价一份 Android 底软 Bug 分析报告。

# 必须遵守
1. **禁止调用任何工具**，不读文件、不执行命令，只依据下方报告正文判断。
2. **只输出一个 JSON 对象**，不要围栏外的任何说明文字。
3. 每条 rubric 都必须给出结论，\`id\` 必须与给定的 id **完全一致**，禁止新增或遗漏。
4. 判断只能基于报告中**实际写出**的内容。报告没写的，一律判不通过，不要替它脑补。
5. \`evidence\` 必须摘录报告原文片段；无法摘录说明该项没有依据，应判不通过。
6. 你是独立评审方，对报告结论没有立场，发现问题就直说。

# 输出 JSON schema
{
  "rubrics": [
    { "id": "root_cause", "pass": true, "score": 0.9, "reason": "判定理由（一句话）", "evidence": "报告原文摘录" }
  ],
  "summary": "整体评价，一到两句"
}

- score: 0–1 达成度，0 表示完全未达成，1 表示完全达成
- pass: 该项是否达到标准（score 高但 pass=false 属于自相矛盾，避免出现）`

  const userMessage = `# 评分标准
${rubricLines}

# 待评报告正文
${reportBody}

请输出 JSON。`

  return { instructions, userMessage }
}

// ─── 纯函数：解析判官输出 ───────────────────────────────────────────────────

/** 判官可能给 0–1 或 0–10，统一归一到 0–1 */
function normalizeScore(raw: unknown, pass: boolean): number {
  if (typeof raw !== 'number' || !Number.isFinite(raw)) return pass ? 1 : 0
  const value = raw > 1 && raw <= 10 ? raw / 10 : raw
  return Math.max(0, Math.min(1, value))
}

export function parseJudgeVerdict(text: string): JudgeVerdict | null {
  if (!text?.trim()) return null
  const parsed = safeParseLLMJSON(text)
  if (!parsed || typeof parsed !== 'object') return null

  const rawRubrics = (parsed as { rubrics?: unknown }).rubrics
  if (!Array.isArray(rawRubrics)) return null

  const rubrics: RubricVerdict[] = []
  for (const item of rawRubrics) {
    if (!item || typeof item !== 'object') continue
    const entry = item as Record<string, unknown>
    const id = String(entry.id ?? '').trim()
    if (!id) continue
    const pass = entry.pass === true
    rubrics.push({
      id,
      pass,
      score: normalizeScore(entry.score, pass),
      reason: String(entry.reason ?? '').trim(),
      evidence: entry.evidence ? String(entry.evidence).trim() : undefined,
    })
  }

  const summaryRaw = (parsed as { summary?: unknown }).summary
  return {
    rubrics,
    summary: summaryRaw ? String(summaryRaw).trim() : undefined,
  }
}

// ─── 纯函数：加权聚合 ───────────────────────────────────────────────────────

function missingVerdict(rubric: Rubric): RubricVerdict {
  return {
    id: rubric.id,
    pass: false,
    score: 0,
    reason: '判官未对该项给出结论',
  }
}

/**
 * 按 rubric 权重聚合。
 * must 项未通过 → 整例 fail（不再看加权分）；rubric 缺判 → 按未通过计。
 */
export function aggregateScore(verdict: JudgeVerdict, rubric: Rubric[]): CaseScore {
  const byId = new Map(verdict.rubrics.map(r => [r.id, r]))
  const resolved: RubricVerdict[] = []
  const mustFailed: string[] = []
  let weightSum = 0
  let weighted = 0

  for (const item of rubric) {
    const found = byId.get(item.id) ?? missingVerdict(item)
    resolved.push(found)
    if (item.must && !found.pass) mustFailed.push(item.id)
    const weight = Math.max(0, item.weight)
    weightSum += weight
    weighted += weight * found.score
  }

  const total = weightSum > 0 ? weighted / weightSum : 0

  let caseVerdict: CaseScore['verdict']
  if (mustFailed.length > 0 || rubric.length === 0) {
    caseVerdict = 'fail'
  } else if (total >= PASS_THRESHOLD) {
    caseVerdict = 'pass'
  } else if (total >= WARN_THRESHOLD) {
    caseVerdict = 'warn'
  } else {
    caseVerdict = 'fail'
  }

  return {
    total,
    verdict: caseVerdict,
    must_failed: mustFailed,
    rubrics: resolved,
    summary: verdict.summary,
  }
}

// ─── LLM 调用 ───────────────────────────────────────────────────────────────

export interface JudgeOptions {
  /** 判官模型；不传则取 TAHP_EVAL_JUDGE_MODEL，再不然用 profile 默认模型 */
  judgeModel?: string
  profile?: string
}

export function resolveJudgeModel(opts: JudgeOptions = {}): string | undefined {
  return opts.judgeModel || process.env.TAHP_EVAL_JUDGE_MODEL || undefined
}

/**
 * 判官与被评者应使用不同模型，避免同源偏袒。
 * 解析失败时抛错，由 runner 记为 error 而非低分——判不出来和判得差是两回事。
 */
export async function judgeReport(
  evalCase: EvalCase,
  reportBody: string,
  opts: JudgeOptions = {},
): Promise<CaseScore> {
  if (!reportBody.trim()) {
    throw new Error('报告正文为空，无法评分')
  }

  const { instructions, userMessage } = buildJudgePrompt(evalCase, reportBody)
  const raw = await callTahpLLM(instructions, userMessage, {
    model: resolveJudgeModel(opts),
    profile: opts.profile,
    maxTokens: JUDGE_MAX_TOKENS,
  })

  const verdict = parseJudgeVerdict(raw)
  if (!verdict) {
    throw new Error(`判官输出无法解析为 JSON: ${raw.slice(0, 200)}`)
  }

  return aggregateScore(verdict, evalCase.rubric)
}
