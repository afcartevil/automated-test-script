/**
 * TAHP — 一键配置表单（统一配置中心）
 *
 * 目的：把「常用 Skill 配置」中各 Skill 需要用户填写的凭据/路径去重，
 * 汇总成一份表单。Jira / Gerrit / OpenGrok 共用同一套域账号密码。
 *
 * 落盘：{TAHP工程根}/.tahp/unified-config.json
 * 保存时同步派生：
 *   - .tahp/jira-user-config.json（智能诊断 / jira-ops 复用）
 *   - .tahp-config/gerrit.json（Gerrit Code Review Agent 复用）
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'fs'
import { join } from 'path'
import { logger } from '../logger'
import { tahpPaths } from './paths'
import { writeJiraUserConfig } from './jira-user-config'
import { saveGerritConfig } from './gerrit-credentials'

export type UnifiedConfigFieldType = 'text' | 'password'

export interface UnifiedConfigField {
  key: string
  label: string
  type: UnifiedConfigFieldType
  group: string
  placeholder?: string
  description?: string
  /** 域账号 / 域密码：Jira / Gerrit / OpenGrok 共用 */
  shared?: boolean
  default?: string
}

const GROUP_DOMAIN = '域账号（Jira / Gerrit / OpenGrok 共用）'
const GROUP_FEISHU = '飞书 OpenAPI（可选，用于日志下载）'
const GROUP_LOCAL = '本地环境与工具（可选）'
const GROUP_TONES = 'TONES SCMP（属性 / 配置查询）'

/**
 * 一键配置表单字段（已按「配置清单中各 Skill 需用户配置项」去重）。
 * Jira / Gerrit / OpenGrok 服务器地址为固定值，不在此表单中配置（见 FIXED_SERVER_ADDRESSES）。
 * 字段来源：jira-ops、modem-analysis-local（含 log-pipeline）的 .env 配置项，
 * 以及 tones-scmp 的 scripts/config.yaml 中的 token 字段。
 * 新增/调整字段只需改这里，前端表单与 Agent 提示词会自动跟随。
 */
export const UNIFIED_CONFIG_FIELDS: UnifiedConfigField[] = [
  {
    key: 'domain_account',
    label: '域账号',
    type: 'text',
    group: GROUP_DOMAIN,
    placeholder: '如 zhangsan',
    description: 'Jira、Gerrit、OpenGrok 共用的公司域账号。',
    shared: true,
  },
  {
    key: 'domain_password',
    label: '域密码',
    type: 'password',
    group: GROUP_DOMAIN,
    placeholder: '域账号密码',
    description: 'Jira、Gerrit、OpenGrok 共用的域账号密码。',
    shared: true,
  },
  {
    key: 'feishu_app_id',
    label: '飞书 App ID',
    type: 'text',
    group: GROUP_FEISHU,
    placeholder: 'cli_xxx',
    description: 'FEISHU_APP_ID：飞书文件分享下载用。',
  },
  {
    key: 'feishu_app_secret',
    label: '飞书 App Secret',
    type: 'password',
    group: GROUP_FEISHU,
    placeholder: 'App Secret',
    description: 'FEISHU_APP_SECRET。',
  },
  {
    key: 'workspace_root',
    label: '工作区路径',
    type: 'text',
    group: GROUP_LOCAL,
    placeholder: '如 D:\\modem_workspace',
    description: 'WORKSPACE_ROOT：日志下载/分析的本地工作区根目录（建议本地 SSD）。',
  },
  {
    key: 'seven_zip_exe',
    label: '7-Zip 可执行路径',
    type: 'text',
    group: GROUP_LOCAL,
    placeholder: '如 C:\\Program Files\\7-Zip\\7z.exe',
    description: 'SEVEN_ZIP_EXE：解压 .rar/.7z 加密/分卷日志包所需。',
  },
  {
    key: 'chrome_binary',
    label: 'Chrome 可执行路径',
    type: 'text',
    group: GROUP_LOCAL,
    placeholder: '如 C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    description: 'CHROME_BINARY：Box 浏览器兜底下载用。',
  },
  {
    key: 'wireshark_path',
    label: 'Wireshark 路径',
    type: 'text',
    group: GROUP_LOCAL,
    placeholder: '如 C:\\Program Files\\Wireshark',
    description: 'WIRESHARK_PATH：modem pcap 转文本用。',
  },
  {
    key: 'elt_home',
    label: 'ELT_HOME',
    type: 'text',
    group: GROUP_LOCAL,
    placeholder: 'MTK ELT 工具目录',
    description: 'ELT_HOME：MTK modem trace 导出用。',
  },
  {
    key: 'nlt_home',
    label: 'NLT_HOME',
    type: 'text',
    group: GROUP_LOCAL,
    placeholder: 'NLT 工具目录',
    description: 'NLT_HOME：modem trace 导出用。',
  },
  {
    key: 'quts_python_path',
    label: 'QUTS Python 路径',
    type: 'text',
    group: GROUP_LOCAL,
    placeholder: '如 C:\\Program Files\\Qualcomm\\QUTS\\Support\\python',
    description: 'QUTS_PYTHON_PATH：Qualcomm QUTS modem log 导出用。',
  },
  {
    key: 'tones_scmp_auth',
    label: 'TONES SCMP Token（p-auth / authorization）',
    type: 'password',
    group: GROUP_TONES,
    placeholder: '如 r_Mjg3...',
    description:
      '写入 tones-scmp 的 scripts/config.yaml：auth_profiles.hk-intra-paas.p_auth 与 authorization（两者同值）。从浏览器 DevTools 请求头 p-auth 复制。',
  },
  {
    key: 'tones_scmp_rtoken',
    label: 'TONES SCMP p-rtoken',
    type: 'password',
    group: GROUP_TONES,
    placeholder: '如 u_Mjg3...',
    description:
      '写入 tones-scmp 的 scripts/config.yaml：auth_profiles.hk-intra-paas.p_rtoken。从浏览器 DevTools 请求头 p-rtoken 复制。',
  },
]

/** 固定服务器地址：不在表单中配置，供 Agent / 派生存储直接使用 */
export const FIXED_SERVER_ADDRESSES = {
  jira_base_url: 'http://jira.transsion.com',
  gerrit_host: 'https://gerrit.transsion.com',
  opengrok_base_url: 'http://opengrok.transsion.com',
} as const

/**
 * 全员通用的 UNC 网络共享凭据（NETWORK_SERVERS）。
 * 团队共性盘配置，不在表单中暴露，由 Agent 直接写入各 Skill 的 .env。
 * 迁移自 skills/.claude/skills/modem-analysis-local/log-pipeline/.env.example。
 * 如需增删共享服务器，改这里即可（唯一权威来源）。
 */
export const FIXED_NETWORK_SERVERS = JSON.stringify([
  { server: '10.205.101.200', share: 'fans_log', username: 'monkeytest', password: 'Monkey123' },
  { server: '10.150.152.37', share: 'fans_log', username: 'monkeytest', password: 'Monkey123' },
  { server: '10.150.152.38', share: 'fans_log', username: 'monkeytest', password: 'Monkey123' },
  { server: '10.150.152.39', share: 'fans_log', username: 'monkeytest', password: 'Monkey123' },
])

/** 表单字段 ↔ Skill .env 变量名映射（用于从已有 Skill 配置默认填充） */
const FIELD_ENV_KEYS: Record<string, string[]> = {
  domain_account: ['JIRA_USERNAME', 'GERRIT_USERNAME'],
  domain_password: ['JIRA_PASSWORD', 'GERRIT_PASSWORD'],
  feishu_app_id: ['FEISHU_APP_ID'],
  feishu_app_secret: ['FEISHU_APP_SECRET'],
  workspace_root: ['WORKSPACE_ROOT'],
  seven_zip_exe: ['SEVEN_ZIP_EXE'],
  chrome_binary: ['CHROME_BINARY'],
  wireshark_path: ['WIRESHARK_PATH'],
  elt_home: ['ELT_HOME'],
  nlt_home: ['NLT_HOME'],
  quts_python_path: ['QUTS_PYTHON_PATH'],
}

/** 按优先级扫描的 Skill .env 文件（相对 skills 根目录），用于默认填充 */
const SKILL_ENV_FILES = [
  'jira-ops/.env',
  'modem-analysis-local/.env',
  'modem-analysis-local/log-pipeline/.env',
]

const SECRET_KEYS = new Set(
  UNIFIED_CONFIG_FIELDS.filter(f => f.type === 'password').map(f => f.key),
)

function parseEnvFile(path: string): Record<string, string> {
  const out: Record<string, string> = {}
  if (!existsSync(path)) return out
  try {
    for (const rawLine of readFileSync(path, 'utf-8').split(/\r?\n/)) {
      const line = rawLine.trim()
      if (!line || line.startsWith('#')) continue
      const eq = line.indexOf('=')
      if (eq <= 0) continue
      const key = line.slice(0, eq).trim()
      let val = line.slice(eq + 1).trim()
      if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith("'") && val.endsWith("'"))) {
        val = val.slice(1, -1)
      }
      if (val) out[key] = val
    }
  } catch {
    /* ignore unreadable .env */
  }
  return out
}

/** 从配置清单各 Skill 已有的真实 .env 中提取默认值（占位/示例 .env.example 不参与） */
function readSkillEnvDefaults(): UnifiedConfigValues {
  const merged: Record<string, string> = {}
  for (const rel of SKILL_ENV_FILES) {
    const env = parseEnvFile(join(tahpPaths.skillsDir, rel))
    for (const [k, v] of Object.entries(env)) {
      if (!(k in merged)) merged[k] = v
    }
  }
  const defaults: UnifiedConfigValues = {}
  for (const field of UNIFIED_CONFIG_FIELDS) {
    for (const envKey of FIELD_ENV_KEYS[field.key] || []) {
      const v = merged[envKey]
      if (v && v.trim()) { defaults[field.key] = v.trim(); break }
    }
  }
  return defaults
}

/**
 * 从 tones-scmp 的 scripts/config.yaml 中提取 token 默认值。
 * config.yaml 非标准 .env，这里只按需抓取 auth_profiles.hk-intra-paas 下的
 * p_auth / authorization / p_rtoken 三个键（简单行匹配，避免引入 yaml 依赖）。
 */
function readTonesScmpDefaults(): UnifiedConfigValues {
  const p = join(tahpPaths.skillsDir, 'tones-scmp', 'scripts', 'config.yaml')
  const out: UnifiedConfigValues = {}
  if (!existsSync(p)) return out
  try {
    const text = readFileSync(p, 'utf-8')
    const pick = (key: string): string => {
      const m = text.match(new RegExp(`^\\s*${key}:\\s*(.+?)\\s*$`, 'm'))
      if (!m) return ''
      let v = m[1].trim()
      if ((v.startsWith('"') && v.endsWith('"')) || (v.startsWith("'") && v.endsWith("'"))) {
        v = v.slice(1, -1)
      }
      return v
    }
    const auth = pick('p_auth') || pick('authorization')
    const rtoken = pick('p_rtoken')
    if (auth) out.tones_scmp_auth = auth
    if (rtoken) out.tones_scmp_rtoken = rtoken
  } catch {
    /* ignore unreadable config.yaml */
  }
  return out
}

export type UnifiedConfigValues = Record<string, string>

function tahpConfigDir(): string {
  const d = join(tahpPaths.projectRoot, '.tahp')
  if (!existsSync(d)) mkdirSync(d, { recursive: true })
  return d
}

export function unifiedConfigPath(): string {
  return join(tahpConfigDir(), 'unified-config.json')
}

export function readUnifiedConfig(): UnifiedConfigValues {
  const p = unifiedConfigPath()
  if (!existsSync(p)) return {}
  try {
    const raw = JSON.parse(readFileSync(p, 'utf-8')) as Record<string, unknown>
    const values: UnifiedConfigValues = {}
    for (const field of UNIFIED_CONFIG_FIELDS) {
      const v = raw[field.key]
      if (typeof v === 'string') values[field.key] = v
    }
    return values
  } catch {
    return {}
  }
}

/**
 * 表单初始展示值：已保存值 > 配置清单各 Skill 已有 .env 默认值 > 字段默认值 > 空。
 * （不落盘覆盖，仅供前端表单预填）
 */
export function readUnifiedConfigForForm(): UnifiedConfigValues {
  const stored = readUnifiedConfig()
  const skillDefaults = { ...readSkillEnvDefaults(), ...readTonesScmpDefaults() }
  const values: UnifiedConfigValues = {}
  for (const field of UNIFIED_CONFIG_FIELDS) {
    const saved = (stored[field.key] || '').trim()
    values[field.key] = saved || skillDefaults[field.key] || field.default || ''
  }
  return values
}

export function writeUnifiedConfig(input: UnifiedConfigValues): UnifiedConfigValues {
  const values: UnifiedConfigValues = {}
  for (const field of UNIFIED_CONFIG_FIELDS) {
    const v = input[field.key]
    values[field.key] = typeof v === 'string' ? v.trim() : ''
  }
  values.__updated_at = new Date().toISOString()
  writeFileSync(unifiedConfigPath(), JSON.stringify(values, null, 2), 'utf-8')
  void propagateToDerivedStores(values).catch((err) => {
    logger.warn({ err: (err as Error).message }, '[unified-config] 派生配置同步失败')
  })
  return values
}

/** 保存后把域账号密码派生到 jira / gerrit 现有存储，保证既有功能无缝复用 */
async function propagateToDerivedStores(values: UnifiedConfigValues): Promise<void> {
  const account = (values.domain_account || '').trim()
  const password = (values.domain_password || '').trim()

  if (account && password) {
    try {
      writeJiraUserConfig({
        username: account,
        password,
        baseUrl: FIXED_SERVER_ADDRESSES.jira_base_url,
      })
    } catch (err) {
      logger.warn({ err: (err as Error).message }, '[unified-config] jira 派生失败')
    }
    try {
      await saveGerritConfig({
        host: FIXED_SERVER_ADDRESSES.gerrit_host,
        user: account,
        password,
      })
    } catch (err) {
      logger.warn({ err: (err as Error).message }, '[unified-config] gerrit 派生失败')
    }
  }
}

export interface UnifiedConfigPublic {
  fields: UnifiedConfigField[]
  values: UnifiedConfigValues
  /** 仅含 unified-config.json 中已落盘的值（不含 .env 预填默认） */
  saved_values: UnifiedConfigValues
  updated_at?: string
}

/** 返回给前端表单：字段 schema + 当前值（含默认值） */
export function getUnifiedConfigPublic(): UnifiedConfigPublic {
  const stored = readUnifiedConfig()
  const savedValues: UnifiedConfigValues = {}
  for (const field of UNIFIED_CONFIG_FIELDS) {
    const v = stored[field.key]
    if (typeof v === 'string') savedValues[field.key] = v
  }
  return {
    fields: UNIFIED_CONFIG_FIELDS,
    values: readUnifiedConfigForForm(),
    saved_values: savedValues,
    updated_at: typeof (stored as any).__updated_at === 'string' ? (stored as any).__updated_at : undefined,
  }
}

export function hasUnifiedConfigValues(): boolean {
  const stored = readUnifiedConfig()
  return UNIFIED_CONFIG_FIELDS.some(f => (stored[f.key] || '').trim().length > 0)
}

/**
 * 供桥接 Agent 系统提示词注入：告知已保存的一键配置表单值，
 * 以便 Skill 缺配置时先复用，而非直接向用户索要。
 * 敏感值（密码/secret）不写明文，只标注"已配置"及可 Read 的文件路径。
 */
export function buildUnifiedConfigDirective(): string {
  const stored = readUnifiedConfig()
  const nonEmpty = UNIFIED_CONFIG_FIELDS.filter(f => (stored[f.key] || '').trim().length > 0)

  const lines: string[] = [
    '# 一键配置表单（缺配置时优先复用）',
    '',
    '当某个 Skill 缺少凭据/路径等配置时，**必须先复用**「配置 → 一键配置表单」中已保存的值；',
    '仅当这些值为空或经验证无效时，才反馈给用户索要。',
    `- 表单落盘文件（含明文，可直接 Read）: \`${join(tahpPaths.projectRoot, '.tahp', 'unified-config.json')}\`（工程根下 \`.tahp/unified-config.json\`）`,
    '- 域账号/域密码在 Jira、Gerrit、OpenGrok 间通用。',
    '- 服务器地址为固定值（无需向用户索要）：'
      + `Jira \`${FIXED_SERVER_ADDRESSES.jira_base_url}\`、`
      + `Gerrit \`${FIXED_SERVER_ADDRESSES.gerrit_host}\`、`
      + `OpenGrok \`${FIXED_SERVER_ADDRESSES.opengrok_base_url}\`。`,
    '- UNC 网络共享凭据为全员通用固定值，需要时直接写入对应 Skill 的 `NETWORK_SERVERS`（无需向用户索要）：',
    `  \`${FIXED_NETWORK_SERVERS}\``,
  ]

  if (nonEmpty.length) {
    lines.push('', '## 已保存的表单项（明文见上述文件）')
    for (const f of nonEmpty) {
      if (SECRET_KEYS.has(f.key)) {
        lines.push(`- ${f.label}（\`${f.key}\`）: 已配置（值见 \`.tahp/unified-config.json\`）`)
      } else {
        lines.push(`- ${f.label}（\`${f.key}\`）: \`${stored[f.key]}\``)
      }
    }
  } else {
    lines.push('', '当前一键配置表单为空；若 Skill 缺配置，请提示用户前往「配置 → 一键配置表单」填写。')
  }

  return lines.join('\n')
}
