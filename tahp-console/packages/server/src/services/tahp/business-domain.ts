/**
 * 业务子域推断 — 基于可配置词典 + module 亲和度评分。
 */
import {
  getBusinessDomainLabel,
  getDomainById,
  listDomainsForModule,
  loadBusinessDomains,
  resolveAliasToDomainId,
  type BusinessDomainDef,
} from './business-domain-registry'

export type { BusinessDomainDef }
export {
  getBusinessDomainLabel,
  listDomainsForModule,
  loadBusinessDomains,
  reloadBusinessDomains,
  resolveAliasToDomainId,
} from './business-domain-registry'

export interface BusinessDomainResult {
  id: string
  label: string
  confidence: number
  source: 'explicit' | 'jira_hint' | 'keyword' | 'module_default' | 'fallback'
}

const MODULE_DEFAULT_DOMAIN: Record<string, string> = {
  telephony: 'general',
  'kernel-driver': 'kernel_driver',
  'power-mgmt': 'power_mgmt',
  shared: 'general',
}

/** 状态栏 + 网络现象 → 网络（避免误归 systemui） */
const DISAMBIGUATION_RULES: Array<{ test: (text: string) => boolean; domainId: string }> = [
  {
    test: t => /状态栏/.test(t) && /无服务|驻网|搜网|registration|plmn|信号/.test(t),
    domainId: 'network',
  },
  {
    test: t => /触摸/.test(t) && /fod|屏下指纹|fingerprint_status/.test(t),
    domainId: 'tp_fod',
  },
  {
    test: t => /花屏|撕裂/.test(t) && /背光|brightness|亮度/.test(t) && !/panel|lcm|dsi/.test(t),
    domainId: 'backlight_power',
  },
]

function result(id: string, confidence: number, source: BusinessDomainResult['source']): BusinessDomainResult {
  const def = getDomainById(id)
  return {
    id: def?.id || id,
    label: def?.label || getBusinessDomainLabel(id),
    confidence,
    source,
  }
}

function domainFromExplicitLabel(text: string): BusinessDomainResult | null {
  const m = text.match(/(?:业务域|问题域|业务分类|子域|分析域|器件域)\s*[:：]\s*([^\n,，;；]+)/i)
  if (m) {
    const id = resolveAliasToDomainId(m[1].trim())
    if (id) return result(id, 0.95, 'explicit')
  }

  const skillM = text.match(/推荐\s*skill\s*[:：]\s*([\w-]+)/i)
  if (skillM) {
    const sid = skillM[1].toLowerCase()
    const skillRules: Array<[RegExp, string]> = [
      [/call|voice|dial|incoming|ecc/, 'voice_call'],
      [/network|signal|plmn|spn|roaming/, 'network'],
      [/data|dstall|datasetup|dataunstable/, 'data'],
      [/apn/, 'apn'],
      [/sim|ussd/, 'sim'],
      [/sms|mms/, 'sms'],
      [/statusbar|systemui|operatorname/, 'systemui'],
      [/mtk-tp|tp-touch|tp_touch|drv_tp|_tp_/, 'tp_touch'],
      [/tp-gesture|gesture/, 'tp_gesture'],
      [/tp-fod|fod/, 'tp_fod'],
      [/vib|vibrator|haptic|richtap/, 'vibrator'],
      [/panel|lcm|backlight-abnormal|screen-tearing/, 'lcm_panel'],
      [/fingerprint|drv-fp|tran_fp/, 'fingerprint'],
      [/audio|aurisys|drv_audio/, 'audio_driver'],
      [/typec|usb|pd-typec|tcpc/, 'typec_usb'],
      [/sensor|als|proximity/, 'sensor_driver'],
      [/charger|gauge|bc12|port-burn|防烧/, 'charging'],
      [/power-standby|wakelock|standby/, 'standby_drain'],
      [/thermal|温升/, 'thermal'],
      [/backlight|brightness/, 'backlight_power'],
      [/display-power|power-key|screen-off/, 'display_power'],
      [/kernel|panic|ke-|oops/, 'kernel_crash'],
      [/bootup|不开机|卡logo/, 'boot'],
    ]
    for (const [re, domainId] of skillRules) {
      if (re.test(sid)) return result(domainId, 0.9, 'explicit')
    }
  }

  return null
}

function scoreDomain(def: BusinessDomainDef, lower: string, text: string, module?: string): number {
  let score = 0

  for (const re of def.jiraHints) {
    if (re.test(text)) score += 12
  }

  for (const kw of def.keywords) {
    const kwLower = kw.toLowerCase()
    if (lower.includes(kwLower)) {
      score += kw.length >= 6 ? 3 : 2
    }
  }

  if (module && module !== 'shared' && def.modules.includes(module)) {
    score += 5
  } else if (
    module && module !== 'shared'
    && !def.modules.includes(module)
    && !def.modules.includes('shared')
    && def.id !== 'general'
  ) {
    score -= 4
  }

  return score
}

export function skillSuggestionGroupKey(module: string, funcType: string, businessDomainId: string): string {
  return `${module}::${funcType}::${businessDomainId}`
}

export interface InferBusinessDomainInput {
  content: string
  module?: string
  tags?: string[]
  jira_key?: string
  business_domain?: string
}

/** 从 JIRA 标题/描述/沉淀报告正文推断业务子域 */
export function inferBusinessDomain(input: InferBusinessDomainInput): BusinessDomainResult {
  if (input.business_domain) {
    const known = getDomainById(input.business_domain)
    if (known) return result(input.business_domain, 1, 'explicit')
    return {
      id: input.business_domain,
      label: input.business_domain,
      confidence: 1,
      source: 'explicit',
    }
  }

  const text = [input.content, (input.tags || []).join(' '), input.jira_key || ''].join('\n')
  const lower = text.toLowerCase()
  const module = input.module?.trim() || undefined

  const explicit = domainFromExplicitLabel(text)
  if (explicit) return explicit

  for (const rule of DISAMBIGUATION_RULES) {
    if (rule.test(text)) return result(rule.domainId, 0.85, 'keyword')
  }

  const candidates = (!module || module === 'shared')
    ? loadBusinessDomains()
    : [...listDomainsForModule(module), ...loadBusinessDomains().filter(d => d.id === 'general')]

  const seen = new Set<string>()
  const pool: BusinessDomainDef[] = []
  for (const d of candidates) {
    if (seen.has(d.id)) continue
    seen.add(d.id)
    pool.push(d)
  }

  let bestId = 'general'
  let bestScore = 0
  let bestSource: BusinessDomainResult['source'] = 'fallback'

  for (const def of pool) {
    if (def.id === 'general') continue
    const score = scoreDomain(def, lower, text, module)
    if (score > bestScore) {
      bestScore = score
      bestId = def.id
      bestSource = score >= 12 ? 'jira_hint' : 'keyword'
    }
  }

  if (bestScore < 2) {
    const fallbackId = module ? (MODULE_DEFAULT_DOMAIN[module] || 'general') : 'general'
    return result(fallbackId, 0.45, 'module_default')
  }

  const confidence = Math.min(0.98, 0.35 + bestScore * 0.04)
  return result(bestId, confidence, bestSource)
}

export interface EntryBusinessDomainShape {
  content: string
  module: string
  tags?: string[]
  jira_key?: string
  business_domain?: string
  business_domain_label?: string
}

export function resolveEntryBusinessDomain(entry: EntryBusinessDomainShape): BusinessDomainResult {
  if (entry.business_domain) {
    const known = getDomainById(entry.business_domain)
    return {
      id: entry.business_domain,
      label: entry.business_domain_label || known?.label || getBusinessDomainLabel(entry.business_domain),
      confidence: 1,
      source: 'explicit',
    }
  }
  return inferBusinessDomain({
    content: entry.content,
    module: entry.module,
    tags: entry.tags,
    jira_key: entry.jira_key,
  })
}

export function assertHomogeneousBusinessDomain(
  entries: EntryBusinessDomainShape[],
): { homogeneous: boolean; domains: BusinessDomainResult[]; dominant: BusinessDomainResult } {
  const domains = entries.map(e => resolveEntryBusinessDomain(e))
  const counts = new Map<string, number>()
  for (const d of domains) counts.set(d.id, (counts.get(d.id) || 0) + 1)
  const sorted = [...counts.entries()].sort((a, b) => b[1] - a[1])
  const dominantId = sorted[0]?.[0] || 'general'
  const dominant = result(dominantId, 1, 'explicit')
  const homogeneous = counts.size <= 1
  return { homogeneous, domains, dominant }
}
