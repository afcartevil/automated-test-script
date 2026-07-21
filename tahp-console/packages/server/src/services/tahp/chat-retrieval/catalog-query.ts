/** 用户问「有哪些案例」类目录查询的识别与领域词扩展 */

const CATALOG_PATTERNS = /有哪些|列出|列表|列举|都有什么|有什么案例|全部案例|相关案例|案例有哪些/i

const CATALOG_STOPWORDS = /有哪些|列出|列表|列举|都有什么|有什么|案例|相关的|相关|的|请|一下|告诉我|查询|搜索|看看|帮我|有|哪些/g

/** 明确「通话」焦点：只用通话子集，避免灌入 SIM/数据/modem 全词袋 */
const CALL_FOCUS = /通话|拨号|语音|来电|去电|接听|呼叫|volte|vowifi|vozwifi|ims/i
const CALL_BROADEN = /sim|modem|apn|短信|彩信|数据|上网|ussd|ecc|运营商|rat/i
const CALL_KEYWORDS = [
  '通话', '拨号', '语音', '来电', '去电', '接听', '呼叫',
  'volte', 'vowifi', 'vozwifi', 'ims', 'call', 'voice', 'telephony', '通信',
]

const DOMAIN_KEYWORDS: Array<{ patterns: RegExp[]; keywords: string[] }> = [
  {
    patterns: [/通话|语音|拨号|来电|去电|接听|呼叫|telephony|vowifi|vozwifi|volte|ims|sim|modem|通信|运营商|rat|ussd|ecc/i],
    keywords: [
      '通话', '通信', 'telephony', 'vowifi', 'vozwifi', 'volte', 'ims', 'sim', 'modem',
      'rat', '拨号', '来电', '去电', 'carrier', '运营商', 'ussd', 'ecc', '紧急',
      'call', 'voice', 'movistar', 'apn',
    ],
  },
  {
    patterns: [/充电|电池|功耗|防烧|port_burn|ntc|背光|hbm|power/i],
    keywords: ['充电', '电池', '功耗', '防烧', 'port_burn', 'ntc', 'power', 'charger', 'battery'],
  },
  {
    patterns: [/驱动|指纹|sensor|driver|内核|kernel|panic/i],
    keywords: ['驱动', '指纹', 'sensor', 'driver', '内核', 'kernel', 'panic'],
  },
]

export function isCatalogQuery(query: string): boolean {
  return CATALOG_PATTERNS.test(query.trim())
}

/** 去掉「有哪些案例」等套话，保留领域关键词 */
export function extractCatalogFocus(query: string): string {
  const stripped = query.trim().replace(CATALOG_STOPWORDS, ' ').replace(/\s+/g, ' ').trim()
  return stripped || query.trim()
}

export function resolveDomainKeywords(query: string, moduleHint?: string): string[] {
  const text = query.trim()
  const set = new Set<string>()

  // 「通信通话常见问题」类：只扩通话子集，不因 moduleHint=telephony 灌全量词袋
  const callFocused = CALL_FOCUS.test(text) && !CALL_BROADEN.test(text)
  if (callFocused) {
    for (const kw of CALL_KEYWORDS) set.add(kw)
  } else {
    for (const { patterns, keywords } of DOMAIN_KEYWORDS) {
      if (patterns.some(p => p.test(text))) {
        for (const kw of keywords) set.add(kw)
      }
    }
    // 仅当正文未命中任何域、且有 telephony hint 时，才用全量通信词作兜底
    if (moduleHint === 'telephony' && set.size === 0) {
      for (const kw of DOMAIN_KEYWORDS[0].keywords) set.add(kw)
    }
  }

  for (const part of text.split(/\s+/)) {
    if (part.length >= 2) set.add(part)
  }

  return [...set]
}
