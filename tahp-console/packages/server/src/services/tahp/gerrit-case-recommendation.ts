/**
 * 根据 Gerrit 评审提取的「必须测试」项，从 week 用例库推荐测试用例。
 * 默认 hybrid：LLM 语义精排 + 规则匹配兜底。
 */

import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { logger } from '../logger'
import { tahpPaths } from './paths'
import { rerankCasesWithLlm } from './gerrit-case-recommend-llm'
import {
  generateAiCasesForCoverageGap,
  normalizeCoverage,
  scoreRuleCoverage,
  type AiGeneratedCase,
  type RecommendCoverage,
} from './gerrit-ai-generated-cases'

const CASE_CONFIG_DIR = join(tahpPaths.selfCheckDir, 'case_config')

export interface RecommendedCase {
  caseKey: string
  caseName: string
  moduleLabel: string
  score: number
  reasons: string[]
}

export interface CaseCandidate {
  caseKey: string
  caseName: string
  moduleLabel: string
}

export interface CatalogDef {
  file: string
  prefix: string
  label: string
}

export type RecommendSource = 'llm' | 'rule'

interface WeekCaseConfig {
  cases?: Array<{ caseIndex: number; caseName: string; [key: string]: unknown }>
}

const MUST_TEST_KEYWORD_HINTS: Record<string, string[]> = {
  USB: ['USB', 'MTP', '充电', '插拔', '枚举', 'adb', '数据线', '充电器'],
  显示: ['显示', '屏幕', '亮度', '背光', '花屏', '黑屏', '闪屏', 'LCM'],
  SIM: ['SIM', '卡', '识别', '注册', '信号'],
  网络: ['网络', '数据', '上网', '5G', '4G', 'LTE'],
  通话: ['通话', '电话', '拨号', '接听'],
  充电: ['充电', '电量', '电池', '快充'],
  指纹: ['指纹', '解锁'],
  相机: ['相机', '拍照', '录像', 'CAMERA'],
  音频: ['音频', '喇叭', '耳机', '录音'],
  传感器: ['传感器', 'SENSOR', 'SAR', '光感', '距离', '距感', 'sensor', '超声'],
}

const DRIVER_CATALOG_HINTS = ['USB', '显示', '充电', '指纹', '相机', '音频', 'LCM', 'TP', '传感器', 'SAR', '插拔', '马达', '触控']
const TDD_CATALOG_HINTS = ['SIM', '通信', '网络', '通话', 'WIFI', '蓝牙', 'GPS', 'NFC', '5G', '4G', '数据']

const MAX_PER_CATALOG = 8

export const FALLBACK_CATALOGS: readonly CatalogDef[] = [
  { file: 'str4_driver_component.json', prefix: 'str4/driver_component', label: '转测驱动' },
]

function recommendMaxTotal(): number {
  const raw = process.env.GERRIT_RECOMMEND_MAX
  if (!raw) return 16
  const value = Number(raw)
  return Number.isFinite(value) && value > 0 ? Math.floor(value) : 16
}

function recommendMode(): 'hybrid' | 'llm' | 'rule' {
  const mode = (process.env.GERRIT_RECOMMEND_MODE || 'hybrid').toLowerCase()
  if (mode === 'llm' || mode === 'rule') return mode
  return 'hybrid'
}

function loadWeekCases(filename: string): Array<{ caseIndex: number; caseName: string }> {
  try {
    const path = join(CASE_CONFIG_DIR, filename)
    const raw = readFileSync(path, 'utf-8')
    const config = JSON.parse(raw) as WeekCaseConfig
    return (config.cases ?? []).filter(c => c?.caseName && c?.caseIndex != null)
  } catch {
    return []
  }
}

export function loadCatalogCases(catalogs: readonly CatalogDef[]): CaseCandidate[] {
  const result: CaseCandidate[] = []
  const seen = new Set<string>()

  for (const cat of catalogs) {
    for (const c of loadWeekCases(cat.file)) {
      const caseKey = `${cat.prefix}/${c.caseIndex}`
      if (seen.has(caseKey)) continue
      seen.add(caseKey)
      result.push({
        caseKey,
        caseName: c.caseName,
        moduleLabel: cat.label,
      })
    }
  }

  return result
}

const GENERIC_TOKEN_STOPWORDS = new Set([
  '检查', '确认', '确保', '验证', '测试', '功能', '正常', '现象', '状态',
  '完成', '成功', '触发', '打印', '并且', '没有', '引发', '死机', '后',
  '反复', '连接', '断开', '读数', '校准', '传感器', '进行', '操作',
])

function isUsefulFallbackToken(token: string): boolean {
  const trimmed = token.trim()
  if (!trimmed) return false
  if (/[A-Za-z0-9]/.test(trimmed)) {
    return trimmed.replace(/[^A-Za-z0-9]/g, '').length >= 2
  }
  if (trimmed.length < 3) return false
  return !GENERIC_TOKEN_STOPWORDS.has(trimmed)
}

function extractFallbackTokens(mustTestItems: string[]): string[] {
  const tokens = new Set<string>()
  for (const item of mustTestItems) {
    const asciiTokens = item.match(/[A-Za-z][A-Za-z0-9_-]*/g) ?? []
    for (const token of asciiTokens) {
      if (isUsefulFallbackToken(token)) tokens.add(token)
    }
    for (const segment of item.split(/[，。；、\s]+/)) {
      const cleaned = segment.replace(/[（）()"“”'']/g, '').trim()
      if (isUsefulFallbackToken(cleaned)) tokens.add(cleaned)
    }
  }
  return [...tokens]
}

function normalizeText(text: string): string {
  return text.toUpperCase().replace(/\s+/g, '')
}

function caseMatchesKeywords(caseName: string, keywords: string[]): boolean {
  const normalized = normalizeText(caseName)
  return keywords.some(kw => normalized.includes(normalizeText(kw)))
}

function normalizeMustTestText(text: string): string {
  return text
    .replace(/\*\*/g, '')
    .replace(/^[\d.\s]+/, '')
    .replace(/\s*[—–-]\s*.+$/, '')
    .replace(/\s*\/\s*验证点:.+$/i, '')
    .trim()
}

export function normalizeMustTestItems(items: string[]): string[] {
  return items
    .map(normalizeMustTestText)
    .filter(Boolean)
}

function caseMatchesPhrase(caseName: string, phrase: string): boolean {
  const normalizedCase = normalizeText(caseName)
  const normalizedPhrase = normalizeText(phrase)
  if (!normalizedPhrase || normalizedPhrase.length < 2) return false
  if (normalizedCase.includes(normalizedPhrase)) return true
  if (normalizedPhrase.length >= 4 && normalizedPhrase.includes(normalizedCase)) return true
  return false
}

function matchMustTest(caseName: string, mustTestItems: string[]): { hit: boolean; reasons: string[] } {
  const reasons: string[] = []
  const cleanedItems = normalizeMustTestItems(mustTestItems)
  const combined = cleanedItems.join(' ')
  for (const [label, keywords] of Object.entries(MUST_TEST_KEYWORD_HINTS)) {
    const mentioned = keywords.some(kw => combined.includes(kw))
    if (mentioned && caseMatchesKeywords(caseName, keywords)) {
      reasons.push(`必须测试:${label}`)
    }
  }
  if (!reasons.length) {
    for (const token of extractFallbackTokens(cleanedItems)) {
      if (caseMatchesKeywords(caseName, [token])) {
        reasons.push(`必须测试:${token.slice(0, 12)}`)
      }
    }
  }
  if (!reasons.length) {
    for (const item of cleanedItems) {
      const head = item.split(/[，。；、/|]/)[0]?.trim() ?? item
      if (head.length >= 2 && caseMatchesPhrase(caseName, head)) {
        reasons.push(`必须测试:${head.slice(0, 12)}`)
      }
    }
  }
  return { hit: reasons.length > 0, reasons: [...new Set(reasons)] }
}

function scoreCase(
  caseName: string,
  mustTestItems: string[],
): { score: number; reasons: string[] } | null {
  if (!mustTestItems.length) return null
  const mustTestResult = matchMustTest(caseName, mustTestItems)
  if (!mustTestResult.hit) return null
  return { score: mustTestResult.reasons.length, reasons: mustTestResult.reasons }
}

function collectFromConfig(
  filename: string,
  caseKeyPrefix: string,
  moduleLabel: string,
  mustTestItems: string[],
  limit: number,
): RecommendedCase[] {
  const cases = loadWeekCases(filename)
  const scored: RecommendedCase[] = []

  for (const c of cases) {
    const result = scoreCase(c.caseName, mustTestItems)
    if (!result) continue
    scored.push({
      caseKey: `${caseKeyPrefix}/${c.caseIndex}`,
      caseName: c.caseName,
      moduleLabel,
      score: result.score,
      reasons: result.reasons,
    })
  }

  scored.sort((a, b) => b.score - a.score)
  return scored.slice(0, limit)
}

export function routeCatalogs(
  mustTestItems: string[],
  modules: string[] = [],
): CatalogDef[] {
  const combined = [...mustTestItems, ...modules].join(' ')
  const wantsDriver = DRIVER_CATALOG_HINTS.some(k => combined.includes(k))
  const wantsTdd = TDD_CATALOG_HINTS.some(k => combined.includes(k))
  const catalogs: CatalogDef[] = []

  if (wantsDriver || !wantsTdd) {
    catalogs.push({ file: 'week_driver.json', prefix: 'week/driver', label: '驱动' })
  }
  if (wantsTdd || !wantsDriver) {
    catalogs.push({ file: 'week_tdd.json', prefix: 'week/tdd', label: '通信' })
  }

  return catalogs
}

export function resolveCandidateCatalogs(
  mustTestItems: string[],
  modules: string[] = [],
): CatalogDef[] {
  const catalogs = routeCatalogs(mustTestItems, modules)
  const candidates = loadCatalogCases(catalogs)
  if (candidates.length) return catalogs
  return [...FALLBACK_CATALOGS]
}

/**
 * 规则匹配推荐（同步，作 fallback）。
 */
export function recommendTestCasesByRules(
  mustTestItems: string[],
  modules: string[] = [],
): RecommendedCase[] {
  const normalizedMustTest = normalizeMustTestItems(mustTestItems)
  if (!normalizedMustTest.length) return []

  const maxTotal = recommendMaxTotal()
  const catalogs = routeCatalogs(normalizedMustTest, modules)
  const all: RecommendedCase[] = []

  for (const cat of catalogs) {
    all.push(
      ...collectFromConfig(
        cat.file,
        cat.prefix,
        cat.label,
        normalizedMustTest,
        MAX_PER_CATALOG,
      ),
    )
  }

  if (!all.length) {
    for (const cat of FALLBACK_CATALOGS) {
      all.push(
        ...collectFromConfig(
          cat.file,
          cat.prefix,
          cat.label,
          normalizedMustTest,
          MAX_PER_CATALOG,
        ),
      )
    }
  }

  all.sort((a, b) => b.score - a.score)
  const seen = new Set<string>()
  const deduped: RecommendedCase[] = []
  for (const item of all) {
    if (seen.has(item.caseKey)) continue
    seen.add(item.caseKey)
    deduped.push(item)
    if (deduped.length >= maxTotal) break
  }

  return deduped
}

/**
 * Hybrid 推荐：LLM 精排优先，失败或空结果时回退规则匹配。
 */
export async function recommendTestCases(
  mustTestItems: string[],
  modules: string[] = [],
): Promise<RecommendedCase[]> {
  const { cases } = await recommendTestCasesWithMeta(mustTestItems, modules)
  return cases
}

export async function recommendTestCasesWithMeta(
  mustTestItems: string[],
  modules: string[] = [],
): Promise<{
  cases: RecommendedCase[]
  source: RecommendSource
  coverage: RecommendCoverage
  aiGeneratedCases: AiGeneratedCase[]
}> {
  const normalizedMustTest = normalizeMustTestItems(mustTestItems)
  if (!normalizedMustTest.length) {
    return {
      cases: [],
      source: 'rule',
      coverage: { score: 1, reason: '未提取到必须测试项，无法评估覆盖度', gaps: [] },
      aiGeneratedCases: [],
    }
  }

  const mode = recommendMode()
  if (mode === 'rule') {
    const cases = recommendTestCasesByRules(normalizedMustTest, modules)
    const coverage = scoreRuleCoverage(normalizedMustTest, cases)
    const aiGeneratedCases = await generateAiCasesSafely(normalizedMustTest, cases, coverage)
    return { cases, source: 'rule', coverage, aiGeneratedCases }
  }

  const maxTotal = recommendMaxTotal()
  const catalogDefs = resolveCandidateCatalogs(normalizedMustTest, modules)
  const candidates = loadCatalogCases(catalogDefs)

  try {
    const llmResultRaw = await rerankCasesWithLlm(
      normalizedMustTest,
      modules,
      candidates,
      maxTotal,
    )
    const llmResult = Array.isArray(llmResultRaw)
      ? { cases: llmResultRaw as RecommendedCase[], coverage: undefined }
      : llmResultRaw
    const llmCases = llmResult.cases
    if (llmCases.length) {
      const fallbackCoverage = scoreRuleCoverage(normalizedMustTest, llmCases)
      const coverage = normalizeCoverage(llmResult.coverage, fallbackCoverage)
      const aiGeneratedCases = await generateAiCasesSafely(normalizedMustTest, llmCases, coverage)
      logger.info(
        {
          source: 'llm',
          p0Count: normalizedMustTest.length,
          recommendedCount: llmCases.length,
          coverageScore: coverage.score,
          aiGeneratedCount: aiGeneratedCases.length,
        },
        '[gerrit-recommend] recommend-cases',
      )
      return { cases: llmCases, source: 'llm', coverage, aiGeneratedCases }
    }
  } catch (err) {
    logger.warn(
      { err: (err as Error).message, mode },
      '[gerrit-recommend] LLM rerank failed, falling back to rules',
    )
  }

  const ruleCases = recommendTestCasesByRules(normalizedMustTest, modules)
  const coverage = scoreRuleCoverage(normalizedMustTest, ruleCases)
  const aiGeneratedCases = await generateAiCasesSafely(normalizedMustTest, ruleCases, coverage)
  logger.info(
    {
      source: 'rule',
      p0Count: normalizedMustTest.length,
      recommendedCount: ruleCases.length,
      mode,
      coverageScore: coverage.score,
      aiGeneratedCount: aiGeneratedCases.length,
    },
    '[gerrit-recommend] recommend-cases',
  )
  return { cases: ruleCases, source: 'rule', coverage, aiGeneratedCases }
}

async function generateAiCasesSafely(
  p0Items: string[],
  cases: RecommendedCase[],
  coverage: RecommendCoverage,
): Promise<AiGeneratedCase[]> {
  if (coverage.score >= 6) {
    logger.info({ coverageScore: coverage.score }, '[gerrit-ai-cases] skip: coverage score >= 6')
    return []
  }
  if (!coverage.gaps.length) {
    logger.info({ coverageScore: coverage.score }, '[gerrit-ai-cases] skip: no coverage gaps')
    return []
  }
  try {
    return await generateAiCasesForCoverageGap(p0Items, cases, coverage)
  } catch (err) {
    logger.warn(
      {
        err: (err as Error).message,
        coverageScore: coverage.score,
        gapCount: coverage.gaps.length,
        gaps: coverage.gaps,
      },
      '[gerrit-ai-cases] generation pipeline failed',
    )
    return []
  }
}
