import type { KbEntryLike } from './types'
import { buildSearchBlob } from './blob'

/**
 * 中英文混合分词：拉丁词按空格切分；连续中文做 2-gram + 关键词片段，避免整句单 token 导致 BM25 失效。
 */
export function tokenize(text: string): string[] {
  const tokens = new Set<string>()
  const normalized = text.toLowerCase().replace(/[^a-z0-9一-龥_]/g, ' ')

  for (const part of normalized.split(/\s+/)) {
    if (!part) continue

    const latin = part.match(/[a-z0-9_]+/gi) || []
    for (const l of latin) {
      if (l.length >= 2) tokens.add(l.toLowerCase())
    }

    const cjkRuns = part.match(/[\u4e00-\u9fff]+/g) || []
    for (const run of cjkRuns) {
      if (run.length <= 6) {
        tokens.add(run)
      } else {
        for (let i = 0; i < run.length - 1; i++) {
          tokens.add(run.slice(i, i + 2))
        }
        for (let len = 3; len <= 4; len++) {
          for (let i = 0; i <= run.length - len; i++) {
            tokens.add(run.slice(i, i + len))
          }
        }
      }
    }
  }

  return [...tokens].filter(t => t.length >= 2)
}

/** 查询与文档 blob 的短语重叠（补充 BM25） */
export function phraseOverlapScore(query: string, blob: string): number {
  const qTokens = tokenize(query)
  const bLower = blob.toLowerCase()
  let hits = 0
  for (const t of qTokens) {
    if (t.length >= 2 && bLower.includes(t)) hits++
  }
  if (qTokens.length === 0) return 0
  return (hits / qTokens.length) * 50
}

/** BM25 Okapi + keyword bonus + confidence boost */
export function calculateRelevance(
  entry: KbEntryLike,
  queryTerms: string[],
  avgDocLen = 200,
): number {
  const k1 = 1.5
  const b = 0.75
  const docText = buildSearchBlob(entry)
  const docTokens = tokenize(docText)
  const docLen = docTokens.length
  const freqMap: Record<string, number> = {}
  for (const t of docTokens) freqMap[t] = (freqMap[t] || 0) + 1

  let score = 0
  for (const term of queryTerms) {
    const tf = freqMap[term] || 0
    if (tf === 0) continue
    const num = tf * (k1 + 1)
    const den = tf + k1 * (1 - b + b * docLen / Math.max(avgDocLen, 1))
    score += num / den
  }

  for (const kw of entry.keywords || []) {
    const kwLow = kw.toLowerCase()
    for (const qt of queryTerms) {
      if (kwLow.includes(qt) || qt.includes(kwLow)) score += 2
    }
  }
  for (const tag of entry.tags || []) {
    const tagLow = tag.toLowerCase()
    for (const qt of queryTerms) {
      if (tagLow.includes(qt) || qt.includes(tagLow)) score += 2.5
    }
  }

  score *= (0.5 + 0.5 * (entry.confidence_score || 0.8))
  return Math.min(100, score * 10)
}
