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
 *   - ~/.tran_asf/env.yaml 或 ~/.tran_harness/env.yaml（asf/harness CLI 复用）
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'fs'
import { join } from 'path'
import { logger } from '../logger'
import { tahpPaths } from './paths'
import { ensureJiraWorkspaceLayout, getJiraWorkspaceRoot } from './jira-workspace'
import { writeJiraUserConfig } from './jira-user-config'
import { saveGerritConfig } from './gerrit-credentials'
import {
  getHarnessEnvPath,
  readHarnessEnvFile,
  syncHarnessEnvFromUnifiedConfig,
} from './harness-env-sync'

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
  /** 字段旁文档超链接（如获取 TOTP 指引） */
  doc_url?: string
  doc_label?: string
}

const GROUP_DOMAIN = '域账号'
const GROUP_HARNESS = 'harness工具'
const GROUP_FEISHU = '飞书 OpenAPI（可选）'
const GROUP_MODEM_TOOLS = 'Modem 工具（可选）'

/** 分组级配置指引（前端一键配置表单展示） */
export const UNIFIED_CONFIG_GROUP_GUIDES: Record<string, { label: string; url: string }> = {
  [GROUP_FEISHU]: {
    label: '获取 App ID / Secret 指引',
    url: 'https://transsioner.feishu.cn/wiki/Hj8ywWYbfiabCqkniEhcCXCynkg',
  },
}

/**
 * 一键配置表单字段（已按「配置清单中各 Skill 需用户配置项」去重）。
 * Jira / Gerrit / OpenGrok 服务器地址为固定值，不在此表单中配置（见 FIXED_SERVER_ADDRESSES）。
 * 字段来源：jira-ops、modem-analysis-local（含 log-pipeline）的 .env 配置项。
 * 新增/调整字段只需改这里，前端表单与 Agent 提示词会自动跟随。
 */
export const UNIFIED_CONFIG_FIELDS: UnifiedConfigField[] = [
  {
    key: 'domain_account',
    label: '域账号',
    type: 'text',
    group: GROUP_DOMAIN,
    placeholder: '公司域账号，Jira / Gerrit / OpenGrok / harness 共用',
    shared: true,
  },
  {
    key: 'domain_password',
    label: '域密码',
    type: 'password',
    group: GROUP_DOMAIN,
    placeholder: '域账号密码（harness：HARNESS_QIZHI_BASTION_PASSWORD 等）',
    shared: true,
  },
  {
    key: 'linux_server_ip',
    label: 'Linux 服务器 IP',
    type: 'text',
    group: GROUP_HARNESS,
    placeholder: '如 10.205.0.143',
    description: 'HARNESS_QIZHI_TARGET_HOST',
  },
  {
    key: 'linux_server_password',
    label: 'Linux 服务器密码',
    type: 'password',
    group: GROUP_HARNESS,
    placeholder: 'SSH / Samba 共享密码',
    description: 'HARNESS_QIZHI_TARGET_PASSWORD、HARNESS_QIZHI_SAMBA_PASSWORD',
  },
  {
    key: 'windows_map_drive',
    label: 'Windows 映射盘目录',
    type: 'text',
    group: GROUP_HARNESS,
    placeholder: 'Z:\\',
    description: 'HARNESS_MAP_DRIVE_ROOT、HARNESS_REMOTE_RUNNER_MAPPED_ROOT',
  },
  {
    key: 'qizhi_totp_secret',
    label: '齐治 TOTP secret',
    type: 'password',
    group: GROUP_HARNESS,
    placeholder: '齐治堡垒机 TOTP base32 secret',
    description: 'HARNESS_QIZHI_OTP_SECRET（Bridge 自动生成动态口令）',
    doc_url: 'https://transsioner.feishu.cn/wiki/Or6RwJ3Vti086Ikt4upcpnFdnWb',
    doc_label: '如何获取',
  },
  {
    key: 'feishu_app_id',
    label: 'App ID',
    type: 'text',
    group: GROUP_FEISHU,
    placeholder: 'cli_xxx',
  },
  {
    key: 'feishu_app_secret',
    label: 'App Secret',
    type: 'password',
    group: GROUP_FEISHU,
    placeholder: '飞书应用密钥',
  },
  {
    key: 'workspace_root',
    label: '工作区路径',
    type: 'text',
    group: GROUP_MODEM_TOOLS,
    placeholder: '默认：{工程根}/jira_workspace',
    description: 'WORKSPACE_ROOT：JIRA 日志下载目录，固定为 {工程根}/jira_workspace（随 clone 路径自动解析）。',
  },
  {
    key: 'seven_zip_exe',
    label: '7-Zip',
    type: 'text',
    group: GROUP_MODEM_TOOLS,
    placeholder: 'C:\\Program Files\\7-Zip\\7z.exe',
    default: 'E:\\software\\7-Zip\\7z.exe',
  },
  {
    key: 'chrome_binary',
    label: 'Chrome',
    type: 'text',
    group: GROUP_MODEM_TOOLS,
    placeholder: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    default: 'C:\\Program Files\\Google\\Chrome\\Application',
  },
  {
    key: 'wireshark_path',
    label: 'Wireshark',
    type: 'text',
    group: GROUP_MODEM_TOOLS,
    placeholder: 'Wireshark 安装目录',
    default: 'E:\\software\\Wireshark',
  },
  {
    key: 'elt_home',
    label: 'ELT_HOME',
    type: 'text',
    group: GROUP_MODEM_TOOLS,
    placeholder: 'MTK ELT 工具目录',
    default: 'E:\\software\\ELT',
  },
  {
    key: 'nlt_home',
    label: 'NLT_HOME',
    type: 'text',
    group: GROUP_MODEM_TOOLS,
    placeholder: 'NLT 工具目录',
    default: 'E:\\software\\ELT',
  },
  {
    key: 'quts_python_path',
    label: 'QUTS Python',
    type: 'text',
    group: GROUP_MODEM_TOOLS,
    placeholder: 'Qualcomm QUTS Python 目录',
    default: 'E:\\software\\ELT',
  },
  {
    key: 'modem_meta_root',
    label: 'Modem Meta',
    type: 'text',
    group: GROUP_MODEM_TOOLS,
    placeholder: '如 D:\\Tool\\MTK\\ModemMeta_v10.2412.0.02_transsion_20240428\\ModemMeta_v10.2412.0.02_transsion_20240428（META.exe 所在目录）',
    description: '填 META.exe 所在安装目录（同级有 bin、configs、plugins 等）。射频校准备份/恢复使用此路径。',
    default: 'E:\\software\\ELT',
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
  domain_account: ['JIRA_USERNAME', 'GERRIT_USERNAME', 'HARNESS_QIZHI_USER'],
  domain_password: ['JIRA_PASSWORD', 'GERRIT_PASSWORD', 'HARNESS_QIZHI_BASTION_PASSWORD'],
  linux_server_ip: ['HARNESS_QIZHI_TARGET_HOST'],
  linux_server_password: ['HARNESS_QIZHI_TARGET_PASSWORD'],
  windows_map_drive: ['HARNESS_MAP_DRIVE_ROOT'],
  qizhi_totp_secret: ['HARNESS_QIZHI_OTP_SECRET'],
  feishu_app_id: ['FEISHU_APP_ID'],
  feishu_app_secret: ['FEISHU_APP_SECRET'],
  workspace_root: ['WORKSPACE_ROOT'],
  seven_zip_exe: ['SEVEN_ZIP_EXE'],
  chrome_binary: ['CHROME_BINARY'],
  wireshark_path: ['WIRESHARK_PATH'],
  elt_home: ['ELT_HOME'],
  nlt_home: ['NLT_HOME'],
  quts_python_path: ['QUTS_PYTHON_PATH'],
  modem_meta_root: ['MODEM_META_ROOT'],
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
  for (const [k, v] of Object.entries(readHarnessEnvFile())) {
    if (!(k in merged)) merged[k] = v
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
 * Modem 工具组字段带团队共用安装路径 default，未自定义时预填，便于保存并启动检查。
 * （不落盘覆盖，仅供前端表单预填；保存时见 fillUnifiedConfigDefaults）
 */
export function readUnifiedConfigForForm(): UnifiedConfigValues {
  const stored = readUnifiedConfig()
  const skillDefaults = readSkillEnvDefaults()
  const values: UnifiedConfigValues = {}
  for (const field of UNIFIED_CONFIG_FIELDS) {
    const saved = (stored[field.key] || '').trim()
    if (field.key === 'workspace_root') {
      values[field.key] = saved || getJiraWorkspaceRoot().replace(/\\/g, '/')
      continue
    }
    if (field.key === 'modem_meta_root') {
      values[field.key] = saved
        || skillDefaults[field.key]
        || process.env.MODEM_META_ROOT?.trim()
        || field.default
        || ''
      continue
    }
    values[field.key] = saved || skillDefaults[field.key] || field.default || ''
  }
  return values
}

/** 用户未填自定义值时回填字段 default；已填值原样保留。工作区路径仍由 write 覆盖为工程根 jira_workspace。 */
export function fillUnifiedConfigDefaults(input: UnifiedConfigValues): UnifiedConfigValues {
  const values: UnifiedConfigValues = {}
  for (const field of UNIFIED_CONFIG_FIELDS) {
    const v = input[field.key]
    const trimmed = typeof v === 'string' ? v.trim() : ''
    values[field.key] = trimmed || field.default || ''
  }
  return values
}

export function writeUnifiedConfig(input: UnifiedConfigValues): UnifiedConfigValues {
  const values: UnifiedConfigValues = fillUnifiedConfigDefaults(input)
  values.__updated_at = new Date().toISOString()
  const workspaceRoot = getJiraWorkspaceRoot()
  values.workspace_root = workspaceRoot.replace(/\\/g, '/')
  writeFileSync(unifiedConfigPath(), JSON.stringify(values, null, 2), 'utf-8')
  void propagateToDerivedStores(values).catch((err) => {
    logger.warn({ err: (err as Error).message }, '[unified-config] 派生配置同步失败')
  })
  try {
    ensureJiraWorkspaceLayout({ workspaceRoot })
  } catch (err) {
    logger.warn({ err: (err as Error).message }, '[unified-config] jira workspace 同步失败')
  }
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
      void import('./sync/jira-bind').then(({ scheduleBindJiraToCentral }) => {
        scheduleBindJiraToCentral({
          username: account,
          password,
          baseUrl: FIXED_SERVER_ADDRESSES.jira_base_url,
        })
      }).catch((bindErr) => {
        logger.warn({ err: (bindErr as Error).message }, '[unified-config] jira-bind schedule failed')
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

  try {
    syncHarnessEnvFromUnifiedConfig(values)
  } catch (err) {
    logger.warn({ err: (err as Error).message }, '[unified-config] harness env 同步失败')
  }
}

export interface UnifiedConfigPublic {
  fields: UnifiedConfigField[]
  values: UnifiedConfigValues
  /** 仅含 unified-config.json 中已落盘的值（不含 .env 预填默认） */
  saved_values: UnifiedConfigValues
  updated_at?: string
  group_guides?: Record<string, { label: string; url: string }>
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
    group_guides: UNIFIED_CONFIG_GROUP_GUIDES,
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
    `- JIRA 日志工作区（WORKSPACE_ROOT）: \`${getJiraWorkspaceRoot().replace(/\\/g, '/')}\`；下载目录为 \`{WORKSPACE_ROOT}/<JIRA_KEY>/\``,
    '- 域账号/域密码在 Jira、Gerrit、OpenGrok、harness（HARNESS_QIZHI_USER / HARNESS_QIZHI_BASTION_PASSWORD 及 Jira/OpenGrok/Gerrit/Spug 凭据）间通用。',
    '- harness 工具：Linux 服务器 IP → `HARNESS_QIZHI_TARGET_HOST`；Linux 服务器密码 → `HARNESS_QIZHI_TARGET_PASSWORD` / `HARNESS_QIZHI_SAMBA_PASSWORD`；Windows 映射盘 → `HARNESS_MAP_DRIVE_ROOT`；齐治 TOTP secret → `HARNESS_QIZHI_OTP_SECRET`。',
    '- Modem 工具：Modem Meta 安装目录 → `modem_meta_root`（射频校准参数备份/恢复）；未配置时引导用户在一键配置表单填写，勿编造路径。',
    '- **使用 asf / harness / 官方 asf-* 或 harness-* skill 前**：先确认 CLI 版本满足工程 \`.tahp/harness-requirement.json\`；不满足则引导用户打开「配置 → 一键配置表单」后点击「启动skill配置检查」。官方 Skill 在本机 `$HOME/.claude/skills` / `$HOME/.cursor/skills` 等，**不在**工程 `skills/`。',
    `- 保存一键配置表单时 BFF 已自动同步 CLI 配置到 \`${getHarnessEnvPath().replace(/\\/g, '/')}\`（旧路径 \`~/.tran_harness/env.yaml\` 若仍存在会一并使用；模板默认值补全未在表单中的项）。`,
    '- 安装/更新 CLI 与 Agent skill：按工程相对路径 `docs/agent-npx-cli-sop.md`（相对 TAHP 工程根）执行；完成后启用全部 capabilities 并 `--sync`。优先命令前缀 `asf`（`harness` 为兼容别名）。',
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
