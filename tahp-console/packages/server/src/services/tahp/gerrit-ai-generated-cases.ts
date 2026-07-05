/**
 * Gerrit Review 低覆盖场景的 AI 用例生成与持久化。
 */
import { randomBytes } from 'node:crypto'
import { existsSync, mkdirSync, readFileSync, writeFileSync, unlinkSync } from 'node:fs'
import { join } from 'node:path'
import {
  AgentBridgeClient,
  getAgentBridgeManager,
  type AgentBridgeOutput,
} from '../hermes/agent-bridge'
import { filterBridgeToolCallMarkupDelta } from '../hermes/run-chat/bridge-delta'
import { logger } from '../logger'
import { tahpPaths } from './paths'
import type { RecommendedCase } from './gerrit-case-recommendation'

const sharedBridgeClient = new AgentBridgeClient({ timeoutMs: 30 * 60_000 })

export const AI_GENERATED_TEST_TYPE = 'ai_generated'
export const AI_GENERATED_MODULE = 'generated'
export const AI_GENERATED_MODULE_LABEL = 'AI生成用例'

const CASE_CONFIG_DIR = join(tahpPaths.selfCheckDir, 'case_config')
const AI_CASE_CONFIG_FILE = join(CASE_CONFIG_DIR, 'ai_generated_generated.json')
const AI_CASE_DIR = join(tahpPaths.selfCheckDir, 'python', 'cases', AI_GENERATED_TEST_TYPE, AI_GENERATED_MODULE)
const AI_CASE_INFO_FILE = join(AI_CASE_DIR, 'case_info.json')

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
  cases: Array<{ caseIndex: number; caseName: string; mode: string; canReuse: boolean }>
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

function aiCaseGenerationTimeoutMs(): number {
  const raw = process.env.GERRIT_AI_CASE_LLM_TIMEOUT_MS
  if (!raw) return 30_000
  const value = Number(raw)
  return Number.isFinite(value) && value > 0 ? value : 30_000
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
  const timeoutSec = Math.ceil(timeoutMs / 1000)

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
      if (Date.now() > deadline) throw new Error('AI 用例生成超时')
    }
    if (!lastChunk?.done) throw new Error('AI 用例生成流意外终止')
    if (lastChunk.error) throw new Error(String(lastChunk.error))
    return fullResponse.trim()
  } finally {
    sharedBridgeClient.destroy(sessionId).catch(() => {})
  }
}

function validatePythonSource(source: string): { ok: boolean; error?: string } {
  const banned = [
    /\bimport\s+(os|subprocess|socket|requests|urllib|http|ftplib|shutil|pathlib|sys)\b/,
    /\bfrom\s+(os|subprocess|socket|requests|urllib|http|ftplib|shutil|pathlib|sys)\b/,
    /\b(eval|exec|compile|open|__import__|input)\s*\(/,
    /\bglobals\s*\(|\blocals\s*\(/,
    /\b(write|unlink|remove|rmdir|mkdir|rename|replace)\s*\(/,
  ]
  if (!/def\s+run\s*\(/.test(source)) return { ok: false, error: '缺少 run(...) 函数' }
  for (const re of banned) {
    if (re.test(source)) return { ok: false, error: `命中危险 Python 语句: ${re}` }
  }
  if (!/return\s+\{/.test(source)) return { ok: false, error: 'run(...) 必须返回 dict 结果' }
  return { ok: true }
}

function ensureAiCaseDirs(): void {
  if (!existsSync(CASE_CONFIG_DIR)) mkdirSync(CASE_CONFIG_DIR, { recursive: true })
  if (!existsSync(AI_CASE_DIR)) mkdirSync(AI_CASE_DIR, { recursive: true })
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
  ensureAiCaseDirs()
  if (!existsSync(AI_CASE_CONFIG_FILE)) return defaultConfig()
  try {
    return { ...defaultConfig(), ...JSON.parse(readFileSync(AI_CASE_CONFIG_FILE, 'utf-8')) }
  } catch {
    return defaultConfig()
  }
}

function saveAiConfig(config: AiGeneratedCaseConfig): void {
  ensureAiCaseDirs()
  writeFileSync(AI_CASE_CONFIG_FILE, `${JSON.stringify(config, null, 2)}\n`, 'utf-8')
}

function loadCaseInfo(): Array<Record<string, unknown>> {
  ensureAiCaseDirs()
  if (!existsSync(AI_CASE_INFO_FILE)) return []
  try {
    const parsed = JSON.parse(readFileSync(AI_CASE_INFO_FILE, 'utf-8'))
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function saveCaseInfo(info: Array<Record<string, unknown>>): void {
  ensureAiCaseDirs()
  writeFileSync(AI_CASE_INFO_FILE, `${JSON.stringify(info, null, 2)}\n`, 'utf-8')
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

  for (const item of config.cases) {
    const pyFile = join(AI_CASE_DIR, `case${item.caseIndex}.py`)
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

function buildGenerationPrompt(p0Items: string[], recommendedCases: RecommendedCase[], coverage: RecommendCoverage) {
  const instructions = `你是 TAHP AI 自检平台的 Python 用例生成助手。根据 Gerrit Review 的 P0 必须测试缺口，生成可由 run_case.py 执行的 Python 用例。

# 必须遵守
1. 禁止调用任何工具，只输出 JSON 对象。
2. Python 只允许定义 run(category=None, case_index=None, device_info=None, **context)。
3. 不允许 import os/subprocess/socket/requests/urllib/http/shutil/pathlib/sys，不允许 eval/exec/open/文件写删除/网络访问。
4. 用例应通过 step_update 输出步骤；需要人工判断时可使用 manual_confirm。
5. 返回 dict: {"status": "pass|fail|pending", "message": "...", "full_automation": false}
6. 生成 1-3 个用例，覆盖推荐用例未覆盖的 P0。`

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
      "pythonSource": "def run(category=None, case_index=None, device_info=None, **context):\\n    ..."
    }
  ]
}`

  return { instructions, userMessage }
}

async function generateNewAiCasesViaLlm(
  p0Items: string[],
  recommendedCases: RecommendedCase[],
  coverage: RecommendCoverage,
): Promise<AiGeneratedCase[]> {
  if (!coverage.gaps.length) return []

  const { instructions, userMessage } = buildGenerationPrompt(p0Items, recommendedCases, coverage)
  logger.info(
    {
      gapCount: coverage.gaps.length,
      gaps: coverage.gaps,
      coverageScore: coverage.score,
    },
    '[gerrit-ai-cases] LLM generation start',
  )

  const raw = await runAiCaseLlmChat(instructions, userMessage)
  const parsed = parseJsonObject(raw)
  if (!parsed) {
    logger.warn({ responsePreview: raw.slice(0, 200) }, '[gerrit-ai-cases] JSON parse failed')
    return []
  }

  const drafts = mapDrafts(parsed)
  if (!drafts.length) {
    logger.warn({ responsePreview: raw.slice(0, 200) }, '[gerrit-ai-cases] no valid drafts in LLM response')
    return []
  }

  const config = loadAiConfig()
  const caseInfo = loadCaseInfo()
  const created: AiGeneratedCase[] = []

  for (const draft of drafts) {
    const validation = validatePythonSource(draft.pythonSource)
    if (!validation.ok) {
      logger.warn({ caseName: draft.caseName, error: validation.error }, '[gerrit-ai-cases] unsafe case rejected')
      continue
    }
    const caseIndex = nextCaseIndex(config)
    const caseKey = `${AI_GENERATED_TEST_TYPE}/${AI_GENERATED_MODULE}/${caseIndex}`
    config.cases.push({ caseIndex, caseName: draft.caseName, mode: 'solo', canReuse: false })
    caseInfo[caseIndex - 1] = {
      用例名: draft.caseName,
      前置条件: '连接测试机，保持设备在线',
      测试步骤: draft.manualSteps || '按 AI 生成脚本提示执行',
      期望结果: draft.expectedResult || '必须测试项得到覆盖验证',
      覆盖P0: draft.coveredP0Items || [],
      生成原因: draft.reason || coverage.reason,
    }
    writeFileSync(join(AI_CASE_DIR, `case${caseIndex}.py`), `${draft.pythonSource.trim()}\n`, 'utf-8')
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
  logger.info({ generatedCount: created.length }, '[gerrit-ai-cases] LLM generation done')
  return created
}

export async function generateAiCasesForCoverageGap(
  p0Items: string[],
  recommendedCases: RecommendedCase[],
  coverage: RecommendCoverage,
): Promise<AiGeneratedCase[]> {
  if (coverage.score >= 6 || coverage.gaps.length === 0) return []

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
    },
    '[gerrit-ai-cases] historical reuse check',
  )

  let generated: AiGeneratedCase[] = []
  if (remainingGaps.length > 0) {
    try {
      generated = await generateNewAiCasesViaLlm(
        p0Items,
        recommendedCases,
        { ...coverage, gaps: remainingGaps },
      )
    } catch (err) {
      logger.warn(
        {
          err: (err as Error).message,
          remainingGapCount: remainingGaps.length,
          remainingGaps,
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
    },
    '[gerrit-ai-cases] generation result',
  )

  return combined
}

export function loadAiGeneratedCaseConfig(): AiGeneratedCaseConfig | null {
  if (!existsSync(AI_CASE_CONFIG_FILE)) return null
  const config = loadAiConfig()
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
    const file = join(AI_CASE_DIR, `case${index}.py`)
    if (existsSync(file)) unlinkSync(file)
    if (info[index - 1]) info[index - 1] = {}
  }
  saveAiConfig(config)
  saveCaseInfo(info)

  const deleted = before === config.cases.length
    ? []
    : normalized.filter(key => indexes.has(Number(key.split('/').pop())))
  return { deleted, remaining: config.cases.length }
}
