export function escapeHtml(text: string) {
  return String(text || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

export function renderSimpleMarkdown(text: string) {
  if (!text) return ''
  let rendered = escapeHtml(text)
    .replace(/\n\n/g, '</p><p>')
    .replace(/\n/g, '<br>')
    .replace(/####\s+(.+)/g, '<h4 class="md-h4">$1</h4>')
    .replace(/###\s+(.+)/g, '<strong class="md-h3">$1</strong>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
  rendered = rendered.replace(/(<li>.*?)(?:<br>)*(?=<li>|$)/gs, '<ul>$1</ul>')
  rendered = rendered.replace(/^[\*\-] (.+?)(?:<br>|$)/gm, '<li>$1</li>')
  return rendered
}

const KEY_RISK_NONE_VALUES = new Set(['无', 'none', 'none.', 'n/a', 'na', '-', '—'])

export function isKeyRiskNone(keyRisk?: string) {
  const raw = String(keyRisk || '').trim()
  if (!raw) return false
  return KEY_RISK_NONE_VALUES.has(raw) || KEY_RISK_NONE_VALUES.has(raw.toLowerCase())
}

/** Human-readable core risk line for UI (replaces bare 「无」). */
export function formatKeyRiskLabel(keyRisk?: string) {
  const raw = String(keyRisk || '').trim()
  if (!raw) return ''
  if (isKeyRiskNone(keyRisk)) return '核心风险：无明显'
  return `核心风险：${raw}`
}

export function keyRiskTone(keyRisk?: string): 'none' | 'risk' {
  return isKeyRiskNone(keyRisk) ? 'none' : 'risk'
}

/** 模块/chunk diff 截断说明（UI 短文案） */
export const DIFF_TRUNCATE_HINT =
  '仅 diff 未全量入模；patch 摘要与高风险片段已覆盖，结论仍可用。'

export interface MarkdownSection {
  id: string
  title: string
  level: number
  content: string
}

function sectionSlug(title: string, index: number) {
  const base = String(title || 'section')
    .trim()
    .slice(0, 32)
    .replace(/[^\w\u4e00-\u9fff-]+/g, '-')
    .replace(/^-+|-+$/g, '')
  return `${index}-${base || 'section'}`
}

/** 按 markdown 标题（## ~ ####）拆分为可折叠章节 */
export function splitMarkdownSections(text: string, headerLevel = 2): MarkdownSection[] {
  const normalized = String(text || '').trim()
  if (!normalized) return []

  const re = new RegExp(`^((?:#{${headerLevel},4})\\s+.+)$`, 'gm')
  const matches = [...normalized.matchAll(re)]
  if (!matches.length) {
    return [{ id: 'body', title: '正文', level: headerLevel, content: normalized }]
  }

  const sections: MarkdownSection[] = []
  const firstIdx = matches[0].index ?? 0
  if (firstIdx > 0) {
    const pre = normalized.slice(0, firstIdx).trim()
    if (pre) {
      sections.push({ id: sectionSlug('概述', 0), title: '概述', level: headerLevel, content: pre })
    }
  }

  matches.forEach((match, index) => {
    const headerLine = match[1]
    const level = (headerLine.match(/^#+/) || ['##'])[0].length
    const title = headerLine.replace(/^#+\s*/, '').trim()
    const start = (match.index ?? 0) + headerLine.length
    const end =
      index + 1 < matches.length ? (matches[index + 1].index ?? normalized.length) : normalized.length
    const content = normalized.slice(start, end).trim()
    sections.push({
      id: sectionSlug(title, sections.length),
      title,
      level,
      content,
    })
  })
  return sections
}

export function splitMarkdownSubSections(content: string, minLevel = 4): MarkdownSection[] {
  const normalized = String(content || '').trim()
  if (!normalized) return []

  const re = new RegExp(`^((?:#{${minLevel}})\\s+.+)$`, 'gm')
  const matches = [...normalized.matchAll(re)]
  if (matches.length < 2) return []

  const sections: MarkdownSection[] = []
  const firstIdx = matches[0].index ?? 0
  if (firstIdx > 0) {
    const pre = normalized.slice(0, firstIdx).trim()
    if (pre) {
      sections.push({ id: sectionSlug('说明', 0), title: '说明', level: minLevel, content: pre })
    }
  }

  matches.forEach((match, index) => {
    const headerLine = match[1]
    const title = headerLine.replace(/^#+\s*/, '').trim()
    const start = (match.index ?? 0) + headerLine.length
    const end =
      index + 1 < matches.length ? (matches[index + 1].index ?? normalized.length) : normalized.length
    const body = normalized.slice(start, end).trim()
    sections.push({
      id: sectionSlug(title, sections.length + 1),
      title,
      level: minLevel,
      content: body,
    })
  })
  return sections
}

export function isLongMarkdown(text: string, threshold = 700) {
  const normalized = String(text || '').trim()
  if (!normalized) return false
  if (normalized.length > threshold) return true
  return normalized.split('\n').length > 10
}

/** Display line for high-risk patch lists (prefers backend ``risk`` / ``reason``). */
export function formatHighRiskReason(item: {
  risk?: string
  reason?: string
  key_risk?: string
  score?: number | string
  recommendation?: string
  blocked?: boolean
  crash_risk?: string
  crash_risk_reason?: string
  block_rules_hit?: string[]
  high_risk_paths?: boolean
}) {
  const primary = String(item.risk || item.reason || '').trim()
  if (primary && !isKeyRiskNone(primary)) return primary

  const parts: string[] = []
  if (item.blocked) {
    const rules = Array.isArray(item.block_rules_hit)
      ? item.block_rules_hit.filter(Boolean).slice(0, 3)
      : []
    parts.push(rules.length ? `触发阻断：${rules.join('、')}` : '触发阻断规则')
  }
  const crash = String(item.crash_risk || '').trim()
  if (crash === '高' || crash === '中') {
    const tail = String(item.crash_risk_reason || '').trim()
    parts.push(tail ? `死机风险${crash}：${tail}` : `死机风险${crash}`)
  }
  if (item.high_risk_paths) parts.push('命中高风险路径')
  const keyRisk = String(item.key_risk || '').trim()
  if (keyRisk && !isKeyRiskNone(keyRisk)) parts.push(keyRisk)
  const rec = String(item.recommendation || '').trim()
  if (rec) parts.push(rec)
  const score = Number(item.score)
  if (Number.isFinite(score) && score > 0) parts.push(`评分 ${score.toFixed(1)}`)

  return parts.join(' · ') || '需优先 review'
}

export function patchScoreColor(score: number | string | undefined) {
  const value = Number(score || 0)
  if (value >= 7) return '#0f766e'
  if (value >= 4) return '#a16207'
  return '#b91c1c'
}

export function formatPatchScore(score: number | string | undefined) {
  const value = Number(score || 0)
  return Number.isFinite(value) ? value.toFixed(1) : '-'
}

export function crashBadgeClass(level?: string) {
  if (level === '高') return 'crash-high'
  if (level === '中') return 'crash-mid'
  return 'crash-low'
}

export function buildModuleStats(patches: any[]) {
  const stats: Record<string, number> = {}
  for (const patch of patches) {
    const mod = patch.dev_module || '其他'
    stats[mod] = (stats[mod] || 0) + 1
  }
  return Object.entries(stats).sort((a, b) => b[1] - a[1])
}

export function patchTagLabels(patch: any) {
  const labels: string[] = []
  if (patch.dev_module) labels.push(patch.dev_module)
  for (const tag of patch.patch_tags || []) {
    if (typeof tag === 'string' && tag) labels.push(tag)
    else if (tag?.label) labels.push(tag.label)
  }
  for (const tag of patch.platform_tags || []) {
    if (typeof tag === 'string' && tag) labels.push(tag)
    else if (tag?.label) labels.push(tag.label)
  }
  return [...new Set(labels)].slice(0, 6)
}

export function hasFutureFix(patch: any) {
  return Array.isArray(patch?.fix_in_future) && patch.fix_in_future.length > 0
}

export function futureFixTags(patch: any) {
  if (!hasFutureFix(patch)) return []
  const tags = new Set<string>()
  for (const fix of patch.fix_in_future) {
    const tag = String(fix?.fix_tag || '').trim()
    if (tag) tags.add(tag)
    for (const t of fix?.fix_tags || []) {
      const s = String(t || '').trim()
      if (s) tags.add(s.replace(/^>/, ''))
    }
  }
  return [...tags].slice(0, 4)
}

export function futureFixIntroSummary(patch: any) {
  const rich = patch?.problem_introducer_rich
  if (rich && typeof rich === 'object' && rich.summary) {
    return String(rich.summary).trim()
  }
  return String(patch?.introducer_analysis || patch?.introduced_risk || '').trim()
}

export function formatFutureFixLine(patch: any) {
  const count = patch?.fix_in_future?.length || 0
  const tags = futureFixTags(patch)
  const tagPart = tags.length ? `，修复于 ${tags.join('、')}` : ''
  return `后续 ${count} 笔 Fixes 修复${tagPart}`
}

export function collectFutureFixPatches(patches: any[]) {
  return (patches || [])
    .filter(hasFutureFix)
    .sort((a, b) => {
      const diff = (b.fix_in_future?.length || 0) - (a.fix_in_future?.length || 0)
      if (diff !== 0) return diff
      return Number(a.score || 0) - Number(b.score || 0)
    })
}

export function patchShaPrefix(patch: any) {
  return String(patch?.sha || patch?.commit || '').trim()
}

/** Resolve a short or full SHA to the full SHA used in the task patch list. */
export function resolvePatchSha(patches: any[], sha: string) {
  const needle = String(sha || '').trim()
  if (!needle) return ''
  const short = needle.slice(0, 12)
  for (const patch of patches || []) {
    const full = patchShaPrefix(patch)
    if (!full) continue
    if (full === needle || full.startsWith(short) || short.startsWith(full.slice(0, 12))) {
      return full
    }
  }
  return ''
}

/** Keep only future-fix summary rows that exist in the current task patch list. */
export function filterFutureFixItemsInPatches(items: any[], patches: any[]) {
  return (items || []).filter((item) => resolvePatchSha(patches, item?.sha || ''))
}

export function buildFutureFixDisplayItem(patch: any) {
  const fixes = patch?.fix_in_future || []
  return {
    sha: patchShaPrefix(patch).slice(0, 12),
    title: String(patch?.title || patch?.subject || '').slice(0, 80),
    score: patch?.score,
    dev_module: String(patch?.dev_module || '').trim(),
    fix_count: fixes.length,
    fix_tags: futureFixTags(patch),
    fix_shas: fixes.map((f: any) => String(f?.sha || '').slice(0, 12)).filter(Boolean).slice(0, 6),
    fix_subjects: fixes
      .map((f: any) => String(f?.subject || f?.title || '').trim().slice(0, 80))
      .filter(Boolean)
      .slice(0, 3),
    introducer_summary: futureFixIntroSummary(patch).slice(0, 220),
    fixes: fixes.slice(0, 8),
  }
}

export type AnalysisNavSection = {
  id: string
  label: string
}

export function hasSummaryTestSuggestions(summary: any) {
  if (String(summary?.test_summary_llm || '').trim()) return true
  const suggestions = summary?.test_suggestions || {}
  return TEST_SUGGESTION_FIELDS.some((field) => (suggestions[field.key] || []).length > 0)
}

/** Same-month ``_rN`` range (e.g. …-2026-01_r11 → …-2026-01_r35): hide monthly subtag section. */
export function isSameMonthSubtagRange(fromTag?: string | null, toTag?: string | null) {
  const re = /^(android\d+-\d+\.\d+-\d{4}-\d{2})_r(\d+)$/
  const fromMatch = String(fromTag || '').trim().match(re)
  const toMatch = String(toTag || '').trim().match(re)
  return Boolean(fromMatch && toMatch && fromMatch[1] === toMatch[1])
}

export function buildAnalysisNavSections(
  summary: any,
  patches: any[] = [],
  monthlyRecommendation: any = null,
): AnalysisNavSection[] {
  const sections: AnalysisNavSection[] = []

  if (monthlyRecommendation?.range_stats?.length) {
    sections.push({ id: 'analysis-section-subtag', label: '子 tag 分析' })
  }

  if (!summary?.total) {
    return sections
  }

  sections.push({ id: 'analysis-section-summary', label: '分析总结' })

  const modulesMap = summary?.module_summaries?.modules || {}
  if (Object.keys(modulesMap).length) {
    sections.push({ id: 'analysis-section-modules', label: '模块分析' })
  }

  if (hasSummaryTestSuggestions(summary)) {
    sections.push({ id: 'analysis-section-tests', label: '测试建议' })
  }

  const futureFixPoolCount = Number(summary?.future_fix_pool_count || 0)
  const futureFixCount =
    filterFutureFixItemsInPatches(summary?.future_fix_patches || [], patches).length ||
    collectFutureFixPatches(patches).length
  if (futureFixCount || futureFixPoolCount) {
    sections.push({ id: 'analysis-section-future-fix', label: '后续修复' })
  }

  if (summary?.high_risk?.length) {
    sections.push({ id: 'analysis-section-high-risk', label: '高风险' })
  }

  if (patches.length) {
    sections.push({ id: 'analysis-section-patches', label: 'Patch 列表' })
  }

  return sections
}

export const TEST_SUGGESTION_FIELDS = [
  { key: 'unit_test', label: '单元测试' },
  { key: 'integration_test', label: '集成测试' },
  { key: 'regression_test', label: '回归测试' },
  { key: 'manual_validation', label: '手工验证' },
  { key: 'release_safeguard', label: '上线保障' },
] as const

export function colorizeDiff(text: string) {
  return escapeHtml(text)
    .split('\n')
    .map((line) => {
      if (line.startsWith('+++') || line.startsWith('---') || line.startsWith('diff ') || line.startsWith('index ')) {
        return `<span class="meta">${line}</span>`
      }
      if (line.startsWith('+') && !line.startsWith('+++')) return `<span class="add">${line}</span>`
      if (line.startsWith('-') && !line.startsWith('---')) return `<span class="del">${line}</span>`
      return line
    })
    .join('\n')
}
