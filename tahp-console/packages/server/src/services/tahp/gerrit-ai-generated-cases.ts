/**
 * Gerrit Review 低覆盖场景的 AI 用例生成与持久化。
 */
import { randomBytes } from 'node:crypto'
import { existsSync } from 'node:fs'
import { join } from 'node:path'
import {
  AgentBridgeClient,
  getAgentBridgeManager,
  type AgentBridgeOutput,
} from '../hermes/agent-bridge'
import { filterBridgeToolCallMarkupDelta } from '../hermes/run-chat/bridge-delta'
import { logger } from '../logger'
import {
  bootstrapAiGeneratedCaseStore,
  clearDurableAiGeneratedStoreIfEmpty,
  loadDurableAiGeneratedConfig,
  loadDurableCaseInfo,
  removeDurableCaseFiles,
  saveDurableAiGeneratedConfig,
  saveDurableCaseInfo,
  writeDurableCasePython,
  getAiGeneratedDurableCaseDir,
} from './ai-generated-case-store'
import type { RecommendedCase } from './gerrit-case-recommendation'

const sharedBridgeClient = new AgentBridgeClient({ timeoutMs: 30 * 60_000 })

/** AI 用例 LLM 生成默认超时（毫秒）；可通过 GERRIT_AI_CASE_LLM_TIMEOUT_MS 覆盖 */
export const DEFAULT_AI_CASE_LLM_TIMEOUT_MS = 120_000

/** Bridge chat 相对流式截止的额外宽限（秒），避免 bridge 先于 stream deadline 断开 */
const AI_CASE_BRIDGE_TIMEOUT_BUFFER_SEC = 30

export const AI_GENERATED_TEST_TYPE = 'ai_generated'
export const AI_GENERATED_MODULE = 'generated'
export const AI_GENERATED_MODULE_LABEL = 'AI生成用例'

export interface RecommendCoverage {
  score: number
  reason: string
  gaps: string[]
}

export interface AiGeneratedCase {
  caseKey: string
  caseIndex: number
  caseName: string
  moduleLabel: string
  coveredP0Items: string[]
  reason: string
  manualSteps: string
  expectedResult: string
}

interface AiGeneratedCaseDraft {
  caseName: string
  coveredP0Items?: string[]
  reason?: string
  pythonSource: string
  manualSteps?: string
  expectedResult?: string
}

interface AiGeneratedCaseConfig {
  testType: string
  module: string
  moduleLabel: string
  conditions: { dutSimCount: number; auxRequired: number; auxSimCount: number }
  defaultCaseMode: string
  cases: Array<{ caseIndex: number; caseName: string; mode: string; canReuse: boolean; execMode?: 'manual' | 'nl_ui' }>
}

function clampCoverageScore(score: number): number {
  if (!Number.isFinite(score)) return 1
  return Math.max(1, Math.min(10, Math.round(score)))
}

export function extractP0MatchTokens(text: string): string[] {
  return [
    ...text.match(/[A-Za-z][A-Za-z0-9_-]*/g) ?? [],
    ...text.split(/[，。；、\s]+/),
  ]
    .map(token => token.replace(/[（）()"“”'']/g, '').trim())
    .filter(token => token.length >= 2)
}

export function textCoversP0Item(p0Item: string, haystack: string): boolean {
  const tokens = extractP0MatchTokens(p0Item)
  if (!tokens.length) return false
  const upper = haystack.toUpperCase()
  return tokens.some(token => upper.includes(token.toUpperCase()))
}

export function scoreRuleCoverage(p0Items: string[], cases: RecommendedCase[]): RecommendCoverage {
  const normalizedP0 = p0Items.map(item => item.trim()).filter(Boolean)
  if (!normalizedP0.length) {
    return { score: 1, reason: '未提取到必须测试项，无法评估覆盖度', gaps: [] }
  }

  const covered = new Set<number>()
  const text = cases.map(c => `${c.caseName} ${c.reasons.join(' ')}`).join('\n')
  normalizedP0.forEach((item, index) => {
    if (textCoversP0Item(item, text)) covered.add(index)
  })

  const ratio = covered.size / normalizedP0.length
  const score = clampCoverageScore(1 + ratio * 9)
  const gaps = normalizedP0.filter((_, index) => !covered.has(index))
  return {
    score,
    reason: score >= 6
      ? `推荐用例覆盖 ${covered.size}/${normalizedP0.length} 个必须测试项，可按推荐用例执行`
      : `推荐用例仅覆盖 ${covered.size}/${normalizedP0.length} 个必须测试项，建议补充 AI 用例`,
    gaps,
  }
}

export function normalizeCoverage(raw: unknown, fallback: RecommendCoverage): RecommendCoverage {
  if (!raw || typeof raw !== 'object') return fallback
  const obj = raw as Record<string, unknown>
  const gaps = Array.isArray(obj.gaps) ? obj.gaps.map(String).filter(Boolean) : fallback.gaps
  return {
    score: clampCoverageScore(Number(obj.score ?? fallback.score)),
    reason: String(obj.reason || fallback.reason),
    gaps,
  }
}

export interface AiCaseGenerationResult {
  cases: AiGeneratedCase[]
  error?: string
}

function aiCaseGenerationTimeoutMs(): number {
  const raw = process.env.GERRIT_AI_CASE_LLM_TIMEOUT_MS
  if (!raw) return DEFAULT_AI_CASE_LLM_TIMEOUT_MS
  const value = Number(raw)
  return Number.isFinite(value) && value > 0 ? value : DEFAULT_AI_CASE_LLM_TIMEOUT_MS
}

export function resolveAiCaseGenerationTimeoutMs(): number {
  return aiCaseGenerationTimeoutMs()
}

function parseJsonObject(text: string): Record<string, unknown> | null {
  const trimmed = text.trim()
  const fenceMatch = trimmed.match(/```(?:json)?\s*([\s\S]*?)```/i)
  const candidate = (fenceMatch?.[1] ?? trimmed).trim()
  try {
    const parsed = JSON.parse(candidate)
    return parsed && typeof parsed === 'object' ? parsed as Record<string, unknown> : null
  } catch {
    const start = trimmed.indexOf('{')
    const end = trimmed.lastIndexOf('}')
    if (start < 0 || end <= start) return null
    try {
      const parsed = JSON.parse(trimmed.slice(start, end + 1))
      return parsed && typeof parsed === 'object' ? parsed as Record<string, unknown> : null
    } catch {
      return null
    }
  }
}

async function runAiCaseLlmChat(instructions: string, userMessage: string): Promise<string> {
  const manager = getAgentBridgeManager()
  if (!manager.running) {
    throw new Error('Agent Bridge 未运行')
  }

  const sessionId = `gerrit-ai-case-${randomBytes(8).toString('hex')}`
  const timeoutMs = aiCaseGenerationTimeoutMs()
  const timeoutSec = Math.ceil(timeoutMs / 1000) + AI_CASE_BRIDGE_TIMEOUT_BUFFER_SEC

  try {
    const started = await sharedBridgeClient.chat(
      sessionId,
      userMessage,
      undefined,
      instructions,
      'default',
      { timeout: timeoutSec, source: 'gerrit-ai-generated-cases' },
    )

    const markupState: { bridgePendingToolCallMarkup?: string } = {}
    let fullResponse = ''
    let lastChunk: AgentBridgeOutput | null = null
    const deadline = Date.now() + timeoutMs

    for await (const chunk of sharedBridgeClient.streamOutput(started.run_id, { intervalMs: 100 })) {
      lastChunk = chunk
      if (chunk.delta) {
        const cleaned = filterBridgeToolCallMarkupDelta(markupState, chunk.delta)
        if (cleaned) fullResponse += cleaned
      }
      if (chunk.done) {
        if (chunk.status === 'error') throw new Error(chunk.error || 'AI 用例生成失败')
        if (chunk.status === 'interrupted') throw new Error('AI 用例生成被中断')
        break
      }
      if (Date.now() > deadline) {
        throw new Error(`AI 用例生成超时（${Math.round(timeoutMs / 1000)}s）`)
      }
    }
    if (!lastChunk?.done) throw new Error('AI 用例生成流意外终止')
    if (lastChunk.error) throw new Error(String(lastChunk.error))
    return fullResponse.trim()
  } finally {
    sharedBridgeClient.destroy(sessionId).catch(() => {})
  }
}

const BANNED_PYTHON_PATTERNS: Array<{ re: RegExp; label: string }> = [
  { re: /^\s*import\s+/m, label: '禁止 import 语句' },
  { re: /^\s*from\s+\w+\s+import\s+/m, label: '禁止 from ... import 语句' },
  { re: /\b(eval|exec|compile|open|__import__|input)\s*\(/, label: '禁止 eval/exec/open 等危险调用' },
  { re: /\bglobals\s*\(|\blocals\s*\(/, label: '禁止 globals/locals' },
  { re: /\b(write|unlink|remove|rmdir|mkdir|rename|replace)\s*\(/, label: '禁止文件系统写操作' },
]

/** AI 生成用例 Python 源码安全校验（供生成流程与单测复用） */
export function validatePythonSource(source: string): { ok: boolean; error?: string } {
  if (!/def\s+run\s*\(/.test(source)) return { ok: false, error: '缺少 run(...) 函数' }
  for (const { re, label } of BANNED_PYTHON_PATTERNS) {
    if (re.test(source)) return { ok: false, error: label }
  }
  if (!/return\s+\{/.test(source)) return { ok: false, error: 'run(...) 必须返回 dict 结果' }
  return { ok: true }
}

const AI_CASE_RUN_TEMPLATE = `def run(category=None, case_index=None, device_info=None, **context):
    step_update = context.get('step_update')
    manual_confirm = context.get('manual_confirm')
    step_update('Step 1: 请确认前置条件。')
    if not manual_confirm('前置条件是否满足？'):
        return {'status': 'fail', 'message': '前置条件未满足', 'full_automation': False}
    step_update('Step 2: 请执行测试操作并观察结果。')
    if manual_confirm('测试结果是否符合预期？'):
        return {'status': 'pass', 'message': '验证通过', 'full_automation': False}
    return {'status': 'fail', 'message': '验证失败', 'full_automation': False}`

function ensureAiCaseDirs(): void {
  bootstrapAiGeneratedCaseStore()
}

function defaultConfig(): AiGeneratedCaseConfig {
  return {
    testType: AI_GENERATED_TEST_TYPE,
    module: AI_GENERATED_MODULE,
    moduleLabel: AI_GENERATED_MODULE_LABEL,
    conditions: { dutSimCount: 0, auxRequired: 0, auxSimCount: 0 },
    defaultCaseMode: 'solo',
    cases: [],
  }
}

function loadAiConfig(): AiGeneratedCaseConfig {
  return loadDurableAiGeneratedConfig()
}

function saveAiConfig(config: AiGeneratedCaseConfig): void {
  saveDurableAiGeneratedConfig(config)
}

function loadCaseInfo(): Array<Record<string, unknown>> {
  return loadDurableCaseInfo()
}

function saveCaseInfo(info: Array<Record<string, unknown>>): void {
  saveDurableCaseInfo(info)
}

function nextCaseIndex(config: AiGeneratedCaseConfig): number {
  const maxIndex = config.cases.reduce((max, item) => Math.max(max, item.caseIndex), 0)
  return maxIndex + 1
}

function mapDrafts(parsed: Record<string, unknown>): AiGeneratedCaseDraft[] {
  const rawCases = Array.isArray(parsed.cases) ? parsed.cases : []
  return rawCases
    .map(item => item as Record<string, unknown>)
    .map(item => ({
      caseName: String(item.caseName || item.case_name || '').trim(),
      coveredP0Items: Array.isArray(item.coveredP0Items) ? item.coveredP0Items.map(String) : [],
      reason: String(item.reason || '').trim(),
      pythonSource: String(item.pythonSource || item.python_source || '').trim(),
      manualSteps: String(item.manualSteps || item.manual_steps || '').trim(),
      expectedResult: String(item.expectedResult || item.expected_result || '').trim(),
    }))
    .filter(item => item.caseName && item.pythonSource)
    .slice(0, 4)
}

function loadHistoricalAiCasesFromDisk(): AiGeneratedCase[] {
  const config = loadAiConfig()
  const info = loadCaseInfo()
  const historical: AiGeneratedCase[] = []
  const caseDir = getAiGeneratedDurableCaseDir()

  for (const item of config.cases) {
    const pyFile = join(caseDir, `case${item.caseIndex}.py`)
    if (!existsSync(pyFile)) continue
    const meta = info[item.caseIndex - 1] ?? {}
    const coveredP0Items = Array.isArray(meta.覆盖P0)
      ? meta.覆盖P0.map(String).filter(Boolean)
      : []
    historical.push({
      caseKey: `${AI_GENERATED_TEST_TYPE}/${AI_GENERATED_MODULE}/${item.caseIndex}`,
      caseIndex: item.caseIndex,
      caseName: item.caseName,
      moduleLabel: AI_GENERATED_MODULE_LABEL,
      coveredP0Items,
      reason: String(meta.生成原因 || '历史 AI 用例'),
      manualSteps: String(meta.测试步骤 || ''),
      expectedResult: String(meta.期望结果 || ''),
    })
  }

  return historical
}

export function findReusableHistoricalAiCases(
  gaps: string[],
  historicalCases?: AiGeneratedCase[],
): { reusable: AiGeneratedCase[]; remainingGaps: string[] } {
  const normalizedGaps = gaps.map(item => item.trim()).filter(Boolean)
  if (!normalizedGaps.length) {
    return { reusable: [], remainingGaps: [] }
  }

  const historical = historicalCases ?? loadHistoricalAiCasesFromDisk()
  if (!historical.length) {
    return { reusable: [], remainingGaps: normalizedGaps }
  }

  const coveredGaps = new Set<string>()
  const reusable: AiGeneratedCase[] = []

  for (const hist of historical) {
    const haystack = [
      hist.caseName,
      hist.reason,
      hist.manualSteps,
      hist.expectedResult,
      ...hist.coveredP0Items,
    ].join(' ')

    const matchedGaps = normalizedGaps.filter(gap => {
      if (coveredGaps.has(gap)) return false
      if (textCoversP0Item(gap, haystack)) return true
      return hist.coveredP0Items.some(
        p0 => textCoversP0Item(gap, p0) || textCoversP0Item(p0, gap),
      )
    })

    if (!matchedGaps.length) continue
    matchedGaps.forEach(gap => coveredGaps.add(gap))
    reusable.push({
      ...hist,
      coveredP0Items: matchedGaps,
      reason: `复用历史 AI 用例，覆盖: ${matchedGaps.join('；')}`,
    })
  }

  return {
    reusable,
    remainingGaps: normalizedGaps.filter(gap => !coveredGaps.has(gap)),
  }
}

function buildGenerationPrompt(
  p0Items: string[],
  recommendedCases: RecommendedCase[],
  coverage: RecommendCoverage,
  retryHint?: string,
) {
  const instructions = `你是 TAHP AI 自检平台的 Python 用例生成助手。根据 Gerrit Review 的 P0 必须测试缺口，生成可由 run_case.py 执行的 Python 用例。

# 必须遵守
1. 禁止调用任何工具，只输出 JSON 对象。
2. Python 只允许定义 run(category=None, case_index=None, device_info=None, **context)。
3. pythonSource 内禁止任何 import / from ... import 语句；禁止 eval/exec/open/文件写删除/网络访问。
4. 只能通过 context.get('step_update') 与 context.get('manual_confirm') 与测试员交互，不得调用 adb/shell/subprocess。
5. 返回 dict: {"status": "pass|fail|pending", "message": "...", "full_automation": false}
6. 生成 1-3 个半自动用例（manual_confirm 引导人工操作），覆盖推荐用例未覆盖的 P0。

# 参考模板（禁止照抄文案，须按缺口改写步骤）
${AI_CASE_RUN_TEMPLATE}`

  const userMessage = `# P0 必须测试
${p0Items.map((item, index) => `${index + 1}. ${item}`).join('\n')}

# 已推荐用例
${recommendedCases.map(c => `- ${c.caseKey} | ${c.caseName} | ${c.reasons.join('；')}`).join('\n') || '无'}

# 覆盖不足
分数: ${coverage.score}
原因: ${coverage.reason}
缺口:
${coverage.gaps.map((item, index) => `${index + 1}. ${item}`).join('\n') || '无'}

# 输出 JSON schema
{
  "cases": [
    {
      "caseName": "验证 XXX",
      "coveredP0Items": ["P0 原文"],
      "reason": "覆盖说明",
      "manualSteps": "1. ...\\n2. ...",
      "expectedResult": "...",
      "pythonSource": "def run(category=None, case_index=None, device_info=None, **context):\\n    step_update = context.get('step_update')\\n    ..."
    }
  ]
}${retryHint ? `\n\n${retryHint}` : ''}`

  return { instructions, userMessage }
}

interface LlmGenerationOutcome {
  cases: AiGeneratedCase[]
  error?: string
}

function persistValidatedDrafts(
  drafts: AiGeneratedCaseDraft[],
  coverage: RecommendCoverage,
): { cases: AiGeneratedCase[]; rejections: string[] } {
  const config = loadAiConfig()
  const caseInfo = loadCaseInfo()
  const created: AiGeneratedCase[] = []
  const rejections: string[] = []

  for (const draft of drafts) {
    const validation = validatePythonSource(draft.pythonSource)
    if (!validation.ok) {
      const reason = `${draft.caseName}: ${validation.error}`
      rejections.push(reason)
      logger.warn({ caseName: draft.caseName, error: validation.error }, '[gerrit-ai-cases] unsafe case rejected')
      continue
    }
    const caseIndex = nextCaseIndex(config)
    const caseKey = `${AI_GENERATED_TEST_TYPE}/${AI_GENERATED_MODULE}/${caseIndex}`
    config.cases.push({ caseIndex, caseName: draft.caseName, mode: 'solo', canReuse: false, execMode: 'manual' })
    caseInfo[caseIndex - 1] = {
      用例名: draft.caseName,
      前置条件: '连接测试机，保持设备在线',
      测试步骤: draft.manualSteps || '按 AI 生成脚本提示执行',
      期望结果: draft.expectedResult || '必须测试项得到覆盖验证',
      覆盖P0: draft.coveredP0Items || [],
      生成原因: draft.reason || coverage.reason,
      execMode: 'manual',
    }
    writeDurableCasePython(caseIndex, `${draft.pythonSource.trim()}\n`)
    created.push({
      caseKey,
      caseIndex,
      caseName: draft.caseName,
      moduleLabel: AI_GENERATED_MODULE_LABEL,
      coveredP0Items: draft.coveredP0Items || [],
      reason: draft.reason || coverage.reason,
      manualSteps: draft.manualSteps || '',
      expectedResult: draft.expectedResult || '',
    })
  }

  if (created.length) {
    saveAiConfig(config)
    saveCaseInfo(caseInfo)
  }
  return { cases: created, rejections }
}

async function generateNewAiCasesViaLlm(
  p0Items: string[],
  recommendedCases: RecommendedCase[],
  coverage: RecommendCoverage,
): Promise<LlmGenerationOutcome> {
  if (!coverage.gaps.length) return { cases: [] }

  const { instructions } = buildGenerationPrompt(p0Items, recommendedCases, coverage)
  logger.info(
    {
      gapCount: coverage.gaps.length,
      gaps: coverage.gaps,
      coverageScore: coverage.score,
    },
    '[gerrit-ai-cases] LLM generation start',
  )

  let retryHint: string | undefined
  for (let attempt = 1; attempt <= 2; attempt++) {
    const { userMessage } = buildGenerationPrompt(p0Items, recommendedCases, coverage, retryHint)
    const raw = await runAiCaseLlmChat(instructions, userMessage)
    const parsed = parseJsonObject(raw)
    if (!parsed) {
      const preview = raw.slice(0, 200)
      logger.warn({ responsePreview: preview, attempt }, '[gerrit-ai-cases] JSON parse failed')
      return { cases: [], error: 'AI 用例响应无法解析为 JSON' }
    }

    const drafts = mapDrafts(parsed)
    if (!drafts.length) {
      const preview = raw.slice(0, 200)
      logger.warn({ responsePreview: preview, attempt }, '[gerrit-ai-cases] no valid drafts in LLM response')
      return { cases: [], error: 'AI 用例响应中无有效 cases' }
    }

    const { cases, rejections } = persistValidatedDrafts(drafts, coverage)
    if (cases.length > 0) {
      logger.info({ generatedCount: cases.length, attempt }, '[gerrit-ai-cases] LLM generation done')
      return { cases }
    }

    if (attempt === 1 && rejections.length > 0) {
      retryHint = [
        '# 上次生成未通过安全校验（请修正 pythonSource 后重试）',
        ...rejections.map(item => `- ${item}`),
        '要求：不得包含任何 import/from 语句；仅使用 context.get("step_update") 与 context.get("manual_confirm")。',
      ].join('\n')
      logger.warn({ attempt, rejections }, '[gerrit-ai-cases] all drafts rejected, retrying LLM')
      continue
    }

    const error = rejections.length
      ? `AI 用例校验未通过：${rejections[0]}`
      : 'AI 用例校验未通过：无有效用例'
    logger.warn({ attempt, rejections }, '[gerrit-ai-cases] LLM generation produced no valid cases')
    return { cases: [], error }
  }

  return { cases: [], error: 'AI 用例生成失败' }
}

export async function generateAiCasesForCoverageGap(
  p0Items: string[],
  recommendedCases: RecommendedCase[],
  coverage: RecommendCoverage,
): Promise<AiCaseGenerationResult> {
  if (coverage.score >= 6 || coverage.gaps.length === 0) {
    return { cases: [] }
  }

  const historical = loadHistoricalAiCasesFromDisk()
  const { reusable, remainingGaps } = findReusableHistoricalAiCases(coverage.gaps, historical)

  logger.info(
    {
      coverageScore: coverage.score,
      gapCount: coverage.gaps.length,
      historicalCount: historical.length,
      reusedCount: reusable.length,
      remainingGapCount: remainingGaps.length,
      remainingGaps,
      timeoutMs: aiCaseGenerationTimeoutMs(),
    },
    '[gerrit-ai-cases] historical reuse check',
  )

  let generated: AiGeneratedCase[] = []
  let generationError: string | undefined
  if (remainingGaps.length > 0) {
    try {
      const llmResult = await generateNewAiCasesViaLlm(
        p0Items,
        recommendedCases,
        { ...coverage, gaps: remainingGaps },
      )
      generated = llmResult.cases
      if (!generated.length && llmResult.error) {
        generationError = llmResult.error
      }
    } catch (err) {
      generationError = (err as Error).message
      logger.warn(
        {
          err: generationError,
          remainingGapCount: remainingGaps.length,
          remainingGaps,
          timeoutMs: aiCaseGenerationTimeoutMs(),
        },
        '[gerrit-ai-cases] LLM generation failed',
      )
    }
  }

  const seen = new Set<string>()
  const combined: AiGeneratedCase[] = []
  for (const item of [...reusable, ...generated]) {
    if (seen.has(item.caseKey)) continue
    seen.add(item.caseKey)
    combined.push(item)
  }

  logger.info(
    {
      reusedCount: reusable.length,
      generatedCount: generated.length,
      totalCount: combined.length,
      error: generationError,
    },
    '[gerrit-ai-cases] generation result',
  )

  const noCases = combined.length === 0
  return {
    cases: combined,
    ...(noCases && generationError ? { error: generationError } : {}),
  }
}

export function loadAiGeneratedCaseConfig(): AiGeneratedCaseConfig | null {
  const config = bootstrapAiGeneratedCaseStore()
  return config.cases.length ? config : null
}

export function deleteAiGeneratedCases(caseKeys: string[]): { deleted: string[]; remaining: number } {
  const normalized = caseKeys.filter(key => key.startsWith(`${AI_GENERATED_TEST_TYPE}/${AI_GENERATED_MODULE}/`))
  if (!normalized.length) return { deleted: [], remaining: loadAiConfig().cases.length }

  const indexes = new Set(
    normalized
      .map(key => Number(key.split('/').pop()))
      .filter(index => Number.isInteger(index) && index > 0),
  )

  const config = loadAiConfig()
  const before = config.cases.length
  config.cases = config.cases.filter(item => !indexes.has(item.caseIndex))
  const info = loadCaseInfo()
  for (const index of indexes) {
    if (info[index - 1]) info[index - 1] = {}
  }
  removeDurableCaseFiles(indexes)
  saveAiConfig(config)
  saveCaseInfo(info)
  clearDurableAiGeneratedStoreIfEmpty(config)

  const deleted = before === config.cases.length
    ? []
    : normalized.filter(key => indexes.has(Number(key.split('/').pop())))
  return { deleted, remaining: config.cases.length }
}
