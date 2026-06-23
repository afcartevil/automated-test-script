/**
 * 业务子域分类 — 用于知识条目分组与 Skill 推荐。
 * 通信类 Bug 按「通话 / 网络 / 数据 / APN / SIM …」拆分，避免不同业务混成一个 Skill。
 */

export interface BusinessDomainDef {
  id: string
  label: string
  /** 优先归属的平台 module */
  modules: string[]
  keywords: string[]
  /** JIRA 组件 / 模块字段常见写法 */
  jiraHints: RegExp[]
}

export interface BusinessDomainResult {
  id: string
  label: string
  confidence: number
  source: 'explicit' | 'jira_hint' | 'keyword' | 'module_default' | 'fallback'
}

export const BUSINESS_DOMAINS: BusinessDomainDef[] = [
  {
    id: 'voice_call',
    label: '通话',
    modules: ['telephony'],
    keywords: [
      '通话', '来电', '去电', '拨号', '掉话', '接听', '挂断', 'volte', 'vowifi', 'vonr',
      'ims注册', 'ims 注册', '补充业务', '呼叫转移', '呼叫等待', 'incall', 'telecom',
      'dialing', 'incoming call', 'outgoing call', 'call drop', 'flash_call', 'ecc', '紧急拨号',
    ],
    jiraHints: [/\(com\)\s*call/i, /通话/, /call\s*problem/i, /voice/i, /volte/i, /vowifi/i],
  },
  {
    id: 'network',
    label: '网络',
    modules: ['telephony'],
    keywords: [
      '驻网', '搜网', '信号', '无服务', 'plmn', 'spn', '运营商名称', '漫游', 'rat',
      '制式', '5g', '4g', 'network scan', 'registration', 'data_registration_state',
      'networkscanhelper', '手动选网', '频繁掉网', '无信号',
    ],
    jiraHints: [/\(com\)\s*network/i, /网络问题/, /network/i, /signal/i, /plmn/i, /spn/i],
  },
  {
    id: 'data',
    label: '数据',
    modules: ['telephony'],
    keywords: [
      '数据连接', '上网', '无法上网', 'data call', 'pdp', 'data stall', 'data_stall',
      '移动数据', '蜂窝数据', '数据不稳定', '数据断开', 'ddsswitch', '智能双卡',
      'datasetup', 'dataunstable', 'dataslow', '吞吐',
    ],
    jiraHints: [/\(com\)\s*data/i, /数据连接/, /data\s*stall/i, /mobile\s*data/i],
  },
  {
    id: 'apn',
    label: 'APN',
    modules: ['telephony'],
    keywords: ['apn', '接入点', 'apn配置', 'apn变更', 'apnchange', 'apn界面', 'apn参数'],
    jiraHints: [/apn/i, /接入点/],
  },
  {
    id: 'sim',
    label: 'SIM',
    modules: ['telephony'],
    keywords: [
      'sim', '识卡', '不识卡', '无sim', '双卡', 'imsi', 'iccid', 'pin', 'puk', 'uicc',
      'sim卡', '卡槽', 'ussd', 'simdetect', 'sim recognition',
    ],
    jiraHints: [/\(com\)\s*sim/i, /sim卡/, /sim\s*problem/i, /ussd/i],
  },
  {
    id: 'sms',
    label: '短信彩信',
    modules: ['telephony'],
    keywords: ['短信', '彩信', 'sms', 'mms', '发送短信', '接收短信', 'smssend', 'smsrecv', 'mmssend', 'mmsrecv'],
    jiraHints: [/\(com\)\s*sms/i, /短信/, /彩信/, /\bsms\b/i, /\bmms\b/i],
  },
  {
    id: 'systemui',
    label: '状态栏/SystemUI',
    modules: ['telephony'],
    keywords: [
      '状态栏', 'systemui', 'volte图标', 'vowifi图标', 'hd图标', 'vonr图标', '网络制式图标',
      '信号塔', 'statusbar', 'status bar', '图标显示', '图标不显示', '图标延迟',
    ],
    jiraHints: [/systemui/i, /状态栏/, /status\s*bar/i],
  },
  {
    id: 'carrier_config',
    label: '运营商配置',
    modules: ['telephony'],
    keywords: [
      'carrierconfig', 'carrier config', '运营商配置', '运营商定制', 'carrier customization',
      'mcc', 'mnc', 'mvno', 'esim', 'wifi calling', 'wfc', '运营商移植',
    ],
    jiraHints: [/carrier/i, /运营商配置/, /carrierconfig/i],
  },
  {
    id: 'settings',
    label: '设置',
    modules: ['telephony'],
    keywords: ['settings', '设置', 'sim卡设置', '网络选项', '移动网络设置', '默认卡'],
    jiraHints: [/settings/i, /设置/],
  },
  {
    id: 'charging',
    label: '充电电池',
    modules: ['power-mgmt', 'telephony'],
    keywords: [
      '充电', '电池', 'battery', 'charger', '端口防烧', '防烧', 'ntc', '电量', '续航',
      'batteryservice', 'power_supply', '快充', '充电服务',
    ],
    jiraHints: [/\(drv\)\s*charger/i, /充电/, /battery/i, /charger/i],
  },
  {
    id: 'stability',
    label: '稳定性/Modem',
    modules: ['telephony'],
    keywords: ['modem_ee', 'modem ee', 'modem crash', 'baseband unknown', 'assert', 'anr', 'crash', '稳定性'],
    jiraHints: [/modem/i, /stability/i, /稳定性/],
  },
  {
    id: 'kernel_driver',
    label: '内核驱动',
    modules: ['kernel-driver'],
    keywords: ['kernel', '内核', 'driver', '驱动', 'dts', 'gpio', 'i2c', 'spi', 'uart', '中断'],
    jiraHints: [/\(drv\)/i, /kernel/i, /driver/i],
  },
  {
    id: 'power_mgmt',
    label: '功耗管理',
    modules: ['power-mgmt'],
    keywords: ['功耗', 'power', 'suspend', '休眠', 'wakeup', '唤醒', 'thermal', '温升', 'wakelock', '待机'],
    jiraHints: [/power/i, /功耗/, /wakelock/i],
  },
]

const DOMAIN_BY_ID = new Map(BUSINESS_DOMAINS.map(d => [d.id, d]))

const EXPLICIT_LABEL_PATTERNS: Array<{ re: RegExp; domainId: string }> = [
  { re: /(?:业务域|问题域|业务分类|子域|分析域)\s*[:：]\s*(通话|网络|数据|apn|sim|短信|彩信|状态栏|运营商|充电|设置)/i, domainId: '' },
  { re: /推荐\s*skill\s*[:：]\s*[\w-]*(voice|call|network|data|apn|sim|sms|systemui|carrier)/i, domainId: '' },
]

const EXPLICIT_LABEL_MAP: Record<string, string> = {
  通话: 'voice_call',
  网络: 'network',
  数据: 'data',
  apn: 'apn',
  APN: 'apn',
  sim: 'sim',
  SIM: 'sim',
  短信: 'sms',
  彩信: 'sms',
  状态栏: 'systemui',
  运营商: 'carrier_config',
  充电: 'charging',
  设置: 'settings',
}

function domainFromExplicitLabel(text: string): BusinessDomainResult | null {
  const m = text.match(/(?:业务域|问题域|业务分类|子域|分析域)\s*[:：]\s*([^\n,，;；]+)/i)
  if (m) {
    const raw = m[1].trim()
    for (const [label, id] of Object.entries(EXPLICIT_LABEL_MAP)) {
      if (raw.includes(label)) {
        const def = DOMAIN_BY_ID.get(id)!
        return { id, label: def.label, confidence: 0.95, source: 'explicit' }
      }
    }
  }
  const skillM = text.match(/推荐\s*skill\s*[:：]\s*([\w-]+)/i)
  if (skillM) {
    const sid = skillM[1].toLowerCase()
    if (/call|voice|dial|incoming|ecc/.test(sid)) return result('voice_call', 0.9, 'explicit')
    if (/network|signal|plmn|spn|roaming/.test(sid)) return result('network', 0.9, 'explicit')
    if (/data|dstall|datasetup|dataunstable/.test(sid)) return result('data', 0.9, 'explicit')
    if (/apn/.test(sid)) return result('apn', 0.9, 'explicit')
    if (/sim|ussd/.test(sid)) return result('sim', 0.9, 'explicit')
    if (/sms|mms/.test(sid)) return result('sms', 0.9, 'explicit')
    if (/statusbar|systemui|operatorname/.test(sid)) return result('systemui', 0.9, 'explicit')
  }
  return null
}

function result(id: string, confidence: number, source: BusinessDomainResult['source']): BusinessDomainResult {
  const def = DOMAIN_BY_ID.get(id) || { id: 'general', label: '通用' }
  return { id: def.id, label: def.label, confidence, source }
}

export function getBusinessDomainLabel(id: string): string {
  return DOMAIN_BY_ID.get(id)?.label || '通用'
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
  if (input.business_domain && DOMAIN_BY_ID.has(input.business_domain)) {
    return result(input.business_domain, 1, 'explicit')
  }

  const text = [
    input.content,
    (input.tags || []).join(' '),
    input.jira_key || '',
  ].join('\n')
  const lower = text.toLowerCase()

  const explicit = domainFromExplicitLabel(text)
  if (explicit) return explicit

  // 状态栏上的网络类现象应归「网络」而非「状态栏」
  if (/状态栏/.test(text) && /无服务|驻网|搜网|registration|plmn|信号/.test(text)) {
    return result('network', 0.85, 'keyword')
  }

  let bestId = 'general'
  let bestScore = 0
  let bestSource: BusinessDomainResult['source'] = 'fallback'

  for (const def of BUSINESS_DOMAINS) {
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

    if (input.module && def.modules.includes(input.module)) {
      score += 1
    }

    if (score > bestScore) {
      bestScore = score
      bestId = def.id
      bestSource = score >= 12 ? 'jira_hint' : 'keyword'
    }
  }

  if (bestScore < 2) {
    if (input.module === 'kernel-driver') return result('kernel_driver', 0.5, 'module_default')
    if (input.module === 'power-mgmt') return result('power_mgmt', 0.5, 'module_default')
    return result('general', 0.2, 'fallback')
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

/** 解析条目业务子域（优先已存储字段，否则实时推断） */
export function resolveEntryBusinessDomain(entry: EntryBusinessDomainShape): BusinessDomainResult {
  if (entry.business_domain && DOMAIN_BY_ID.has(entry.business_domain)) {
    return {
      id: entry.business_domain,
      label: entry.business_domain_label || getBusinessDomainLabel(entry.business_domain),
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

/** 检测一组条目是否属于同一业务子域 */
export function assertHomogeneousBusinessDomain(
  entries: EntryBusinessDomainShape[],
): { homogeneous: boolean; domains: BusinessDomainResult[]; dominant: BusinessDomainResult } {
  const domains = entries.map(e => resolveEntryBusinessDomain(e))
  const counts = new Map<string, number>()
  for (const d of domains) counts.set(d.id, (counts.get(d.id) || 0) + 1)
  const sorted = [...counts.entries()].sort((a, b) => b[1] - a[1])
  const dominantId = sorted[0]?.[0] || 'general'
  const dominant = result(dominantId, 1, 'explicit')
  const homogeneous = sorted.length <= 1 || (sorted.length === 2 && sorted[1][1] === 0)
  return { homogeneous, domains, dominant }
}
