/**
 * 根据 Gerrit 评审提取的「必须测试」项，从 week 用例库推荐测试用例。
 */

import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { tahpPaths } from './paths'

const CASE_CONFIG_DIR = join(tahpPaths.selfCheckDir, 'case_config')

export interface RecommendedCase {
  caseKey: string
  caseName: string
  moduleLabel: string
  score: number
  reasons: string[]
}

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
  传感器: ['传感器', 'SENSOR', 'SAR', '光感', '距离', 'sensor'],
}

const DRIVER_CATALOG_HINTS = ['USB', '显示', '充电', '指纹', '相机', '音频', 'LCM', 'TP', '传感器', 'SAR', '插拔', '马达', '触控']
const TDD_CATALOG_HINTS = ['SIM', '通信', '网络', '通话', 'WIFI', '蓝牙', 'GPS', 'NFC', '5G', '4G', '数据']

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

function matchMustTest(caseName: string, mustTestItems: string[]): { hit: boolean; reasons: string[] } {
  const reasons: string[] = []
  const combined = mustTestItems.join(' ')
  for (const [label, keywords] of Object.entries(MUST_TEST_KEYWORD_HINTS)) {
    const mentioned = keywords.some(kw => combined.includes(kw))
    if (mentioned && caseMatchesKeywords(caseName, keywords)) {
      reasons.push(`必须测试:${label}`)
    }
  }
  if (!reasons.length) {
    for (const token of extractFallbackTokens(mustTestItems)) {
      if (caseMatchesKeywords(caseName, [token])) {
        reasons.push(`必须测试:${token.slice(0, 12)}`)
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

function routeCatalogs(mustTestItems: string[]): Array<{ file: string; prefix: string; label: string }> {
  const combined = mustTestItems.join(' ')
  const wantsDriver = DRIVER_CATALOG_HINTS.some(k => combined.includes(k))
  const wantsTdd = TDD_CATALOG_HINTS.some(k => combined.includes(k))
  const catalogs: Array<{ file: string; prefix: string; label: string }> = []

  if (wantsDriver || !wantsTdd) {
    catalogs.push({ file: 'week_driver.json', prefix: 'week/driver', label: '驱动' })
  }
  if (wantsTdd || !wantsDriver) {
    catalogs.push({ file: 'week_tdd.json', prefix: 'week/tdd', label: '通信' })
  }

  return catalogs
}

const MAX_PER_CATALOG = 8
const MAX_TOTAL = 16

/**
 * 根据「必须测试」项推荐 week 用例。
 */
export function recommendTestCases(mustTestItems: string[]): RecommendedCase[] {
  const normalizedMustTest = mustTestItems.map(t => t.trim()).filter(Boolean)
  if (!normalizedMustTest.length) return []

  const catalogs = routeCatalogs(normalizedMustTest)
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

  all.sort((a, b) => b.score - a.score)
  const seen = new Set<string>()
  const deduped: RecommendedCase[] = []
  for (const item of all) {
    if (seen.has(item.caseKey)) continue
    seen.add(item.caseKey)
    deduped.push(item)
    if (deduped.length >= MAX_TOTAL) break
  }

  return deduped
}
