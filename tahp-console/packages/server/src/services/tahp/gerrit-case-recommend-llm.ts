/**
 * Gerrit 用例推荐 — LLM 语义精排（Agent Bridge 轻量调用）
 */

import { randomBytes } from 'node:crypto'
import {
  AgentBridgeClient,
  getAgentBridgeManager,
  type AgentBridgeOutput,
} from '../hermes/agent-bridge'
import { filterBridgeToolCallMarkupDelta } from '../hermes/run-chat/bridge-delta'
import { logger } from '../logger'
import type { RecommendCoverage } from './gerrit-ai-generated-cases'
import type { CaseCandidate, RecommendedCase } from './gerrit-case-recommendation'

const sharedBridgeClient = new AgentBridgeClient({ timeoutMs: 30 * 60_000 })

export interface LlmRecommendationRaw {
  caseKey: string
  score?: number
  reason?: string
}

export interface LlmRecommendJson {
  recommendations: LlmRecommendationRaw[]
  coverage?: {
    score?: number
    reason?: string
    gaps?: string[]
  }
}

export interface LlmRecommendResult {
  cases: RecommendedCase[]
  coverage?: RecommendCoverage
}

function recommendLlmTimeoutMs(): number {
  const raw = process.env.GERRIT_RECOMMEND_LLM_TIMEOUT_MS
  if (!raw) return 20_000
  const value = Number(raw)
  return Number.isFinite(value) && value > 0 ? value : 20_000
}

function normalizeLlmScore(score: unknown): number {
  if (typeof score !== 'number' || !Number.isFinite(score)) return 1
  if (score > 0 && score <= 1) return Math.max(1, Math.round(score * 10))
  if (score > 1 && score <= 10) return Math.round(score)
  if (score > 10) return 10
  return 1
}

export function parseRecommendLlmJson(text: string): LlmRecommendJson | null {
  const trimmed = text.trim()
  if (!trimmed) return null

  const fenceMatch = trimmed.match(/```(?:json)?\s*([\s\S]*?)```/i)
  const candidate = (fenceMatch?.[1] ?? trimmed).trim()

  try {
    return parseRecommendLlmObject(JSON.parse(candidate) as unknown)
  } catch {
    const start = trimmed.indexOf('{')
    const end = trimmed.lastIndexOf('}')
    if (start < 0 || end <= start) return null
    try {
      return parseRecommendLlmObject(JSON.parse(trimmed.slice(start, end + 1)) as unknown)
    } catch {
      return null
    }
  }
}

function parseRecommendLlmObject(parsed: unknown): LlmRecommendJson | null {
  if (!parsed || typeof parsed !== 'object') return null
  const obj = parsed as LlmRecommendJson
  const recs = obj.recommendations
  if (!Array.isArray(recs)) return null
  return {
    recommendations: recs,
    coverage: obj.coverage,
  }
}

export function buildRecommendPrompt(
  p0Items: string[],
  modules: string[],
  candidates: CaseCandidate[],
): { instructions: string; userMessage: string } {
  const p0Block = p0Items.map((item, i) => `${i + 1}. ${item}`).join('\n')
  const moduleLine = modules.length ? modules.join('/') : '未识别'
  const caseLines = candidates
    .map(c => `- ${c.caseKey} | ${c.caseName} | ${c.moduleLabel}`)
    .join('\n')

  const instructions = `你是 TAHP 自检平台的测试用例推荐助手。根据 Gerrit Code Review 的「必须测试」项，从给定候选用例中选出最相关的测试用例。

# 必须遵守
1. **禁止调用任何工具**，不要读取文件，不要执行命令。
2. **只输出一个 JSON 对象**，不要 Markdown 说明、不要代码围栏外的文字。
3. \`caseKey\` 必须**完全匹配**候选列表中的某一项，禁止编造。
4. 按 P0 **验证场景语义**匹配，宁少勿滥，建议 3–8 条，最多 16 条。
5. P0 提到 SAR/校准/传感器时，优先传感器相关用例；勿因出现 USB 就推荐全部充电类用例。
6. 无合适用例时返回空数组：\`{"recommendations":[]}\`

# 输出 JSON schema
{
  "coverage": {
    "score": 6,
    "reason": "推荐用例集合对 P0 的整体覆盖说明",
    "gaps": ["未被推荐用例覆盖的 P0 原文"]
  },
  "recommendations": [
    { "caseKey": "week/driver/14", "score": 0.95, "reason": "与 P0 验证场景匹配的简短理由" }
  ]
}

- score: 0–1 相关性（越高越相关）或 1–10 整数
- reason: 一句话说明为何推荐
- coverage.score: 1–10。1 表示几乎未覆盖，6 表示基本覆盖且可按推荐用例测试，10 表示完全覆盖。`

  const userMessage = `# 变更模块
${moduleLine}

# 必须测试 (P0)
${p0Block}

# 候选用例 (caseKey | caseName | moduleLabel)
${caseLines}

请输出 JSON。`

  return { instructions, userMessage }
}

export function mapLlmRecommendations(
  parsed: LlmRecommendJson,
  candidates: CaseCandidate[],
  maxTotal: number,
): RecommendedCase[] {
  const byKey = new Map(candidates.map(c => [c.caseKey, c]))
  const seen = new Set<string>()
  const result: RecommendedCase[] = []

  for (const item of parsed.recommendations) {
    const caseKey = String(item.caseKey || '').trim()
    if (!caseKey || seen.has(caseKey)) continue
    const candidate = byKey.get(caseKey)
    if (!candidate) continue

    const reason = String(item.reason || '').trim() || 'LLM 语义匹配'
    seen.add(caseKey)
    result.push({
      caseKey,
      caseName: candidate.caseName,
      moduleLabel: candidate.moduleLabel,
      score: normalizeLlmScore(item.score),
      reasons: [reason],
    })
    if (result.length >= maxTotal) break
  }

  result.sort((a, b) => b.score - a.score)
  return result
}

export function mapLlmCoverage(parsed: LlmRecommendJson): RecommendCoverage | undefined {
  const coverage = parsed.coverage
  if (!coverage) return undefined
  const rawScore = Number(coverage.score)
  const score = Number.isFinite(rawScore)
    ? Math.max(1, Math.min(10, Math.round(rawScore)))
    : 1
  return {
    score,
    reason: String(coverage.reason || ''),
    gaps: Array.isArray(coverage.gaps) ? coverage.gaps.map(String).filter(Boolean) : [],
  }
}

async function runRecommendLlmChat(
  instructions: string,
  userMessage: string,
): Promise<string> {
  const manager = getAgentBridgeManager()
  if (!manager.running) {
    throw new Error('Agent Bridge 未运行')
  }

  const sessionId = `gerrit-recommend-${randomBytes(8).toString('hex')}`
  const timeoutSec = Math.ceil(recommendLlmTimeoutMs() / 1000)

  try {
    const started = await sharedBridgeClient.chat(
      sessionId,
      userMessage,
      undefined,
      instructions,
      'default',
      { timeout: timeoutSec, source: 'gerrit-case-recommend' },
    )

    const markupState: { bridgePendingToolCallMarkup?: string } = {}
    let fullResponse = ''
    let lastChunk: AgentBridgeOutput | null = null
    const deadline = Date.now() + recommendLlmTimeoutMs()

    for await (const chunk of sharedBridgeClient.streamOutput(started.run_id, { intervalMs: 100 })) {
      lastChunk = chunk
      if (chunk.delta) {
        const cleaned = filterBridgeToolCallMarkupDelta(markupState, chunk.delta)
        if (cleaned) fullResponse += cleaned
      }
      if (chunk.done) {
        if (chunk.status === 'error') {
          throw new Error(chunk.error || 'LLM 推荐调用失败')
        }
        if (chunk.status === 'interrupted') {
          throw new Error('LLM 推荐被中断')
        }
        break
      }
      if (Date.now() > deadline) {
        throw new Error('LLM 推荐超时')
      }
    }

    if (!lastChunk?.done) {
      throw new Error('LLM 推荐流意外终止')
    }
    if (lastChunk.error) {
      throw new Error(String(lastChunk.error))
    }

    return fullResponse.trim()
  } finally {
    sharedBridgeClient.destroy(sessionId).catch(() => {})
  }
}

export async function rerankCasesWithLlm(
  p0Items: string[],
  modules: string[],
  candidates: CaseCandidate[],
  maxTotal: number,
): Promise<LlmRecommendResult> {
  if (!p0Items.length || !candidates.length) return { cases: [] }

  const { instructions, userMessage } = buildRecommendPrompt(p0Items, modules, candidates)
  const raw = await runRecommendLlmChat(instructions, userMessage)
  const parsed = parseRecommendLlmJson(raw)
  if (!parsed) {
    logger.warn(
      { responsePreview: raw.slice(0, 200) },
      '[gerrit-recommend] LLM JSON parse failed',
    )
    return { cases: [] }
  }

  const cases = mapLlmRecommendations(parsed, candidates, maxTotal)
  return {
    cases,
    coverage: mapLlmCoverage(parsed),
  }
}
