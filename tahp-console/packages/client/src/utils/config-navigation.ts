export type ConfigTab = 'models' | 'form' | 'batch'

export const CONFIG_ROUTE_NAME = 'tahp.config'

/** 一键配置检查页「启动」按钮文案 */
export const SKILL_CONFIG_CHECK_BUTTON_LABEL = '启动skill配置检查'

/** 一键配置页合并按钮：先保存再启动检查 */
export const SAVE_AND_START_SKILL_CHECK_LABEL = '保存并启动skill配置检查'

export const CONFIG_TAB_LABELS: Record<Exclude<ConfigTab, 'batch'>, string> = {
  models: '模型管理',
  form: '一键配置',
}

/** 配置页可见的主 Tab（batch 是一键配置内的检查步） */
export const CONFIG_MAIN_TABS: Array<Exclude<ConfigTab, 'batch'>> = ['models', 'form']

export function parseConfigTab(raw: unknown): ConfigTab {
  if (raw === 'batch') return 'batch'
  // 旧「常用 Skill 配置」并入一键配置
  if (raw === 'form' || raw === 'skills') return 'form'
  return 'models'
}

/** 表单步与检查步都属于「一键配置」标签 */
export function isConfigSetupTab(tab: ConfigTab): boolean {
  return tab === 'form' || tab === 'batch'
}

/** 已保存配置中是否至少有一项表单字段非空 */
export function hasAnySavedFormValue(
  savedValues: Record<string, string>,
  fields: Array<{ key: string }>,
): boolean {
  return fields.some(f => (savedValues[f.key] || '').trim().length > 0)
}

export function isFormFieldFilled(value: string | undefined): boolean {
  return (value || '').trim().length > 0
}

/** 当前值为空的表单字段（全部视为必填） */
export function listUnfilledFormFields<T extends { key: string }>(
  values: Record<string, string | undefined>,
  fields: T[],
): T[] {
  return fields.filter(f => !isFormFieldFilled(values[f.key]))
}

/** 测试域账号前缀：命中后只保存凭据，不启动 skill 配置检查 */
export const TEST_DOMAIN_ACCOUNT_PREFIX = 'test-'

/** 测试域账号固定密码 */
export const TEST_DOMAIN_PASSWORD = '12345678'

/** 测试域账号保存后的提示：不启动检查 */
export const TEST_DOMAIN_SAVE_ONLY_HINT = '测试账号：已保存域账号与域密码；其余配置项未完成，未启动 skill 配置检查'

/** 是否为测试域账号（test- 前缀 + 固定测试密码）；此类账号允许缺项保存，但不启动检查 */
export function isTestDomainCredential(values: Record<string, string | undefined>): boolean {
  const account = (values.domain_account || '').trim().toLowerCase()
  const password = (values.domain_password || '').trim()
  return account.startsWith(TEST_DOMAIN_ACCOUNT_PREFIX) && password === TEST_DOMAIN_PASSWORD
}

function groupDisplayName(group: string | undefined): string {
  return (group || '').replace(/（可选）/g, '').trim()
}

/** 缺填提示：列出未填字段（含分组） */
export function formatUnfilledFieldsHint(fields: Array<{ group?: string; label: string }>): string {
  if (!fields.length) return '请填写全部配置项'
  const items = fields.map((f) => {
    const group = groupDisplayName(f.group)
    return group ? `${group} · ${f.label}` : f.label
  })
  const max = 6
  const preview = items.slice(0, max).join('；')
  if (items.length > max) {
    return `请填写全部配置项（缺 ${items.length} 项）：${preview}…`
  }
  return `请填写全部配置项（缺 ${items.length} 项）：${preview}`
}

export type SkillSetupKind = 'running' | 'all' | 'partial' | 'failed' | 'none'

export interface SkillSetupSummary {
  kind: SkillSetupKind
  configured: number
  total: number
  label: string
  tone: 'ok' | 'warn' | 'err' | 'info' | 'muted'
  showLiveHint: boolean
}

/** 一键配置页 Skill 状态条：清单计数 + 可选上次整表检查结果 */
export function summarizeSkillSetup(input: {
  skills: Array<{ status?: string }>
  batchRunning?: boolean
  lastCheckOk?: boolean | null
}): SkillSetupSummary {
  const total = input.skills.length
  const configured = input.skills.filter(s => s.status === 'configured').length
  const counts = `${configured}/${total}`

  if (input.batchRunning) {
    return {
      kind: 'running',
      configured,
      total,
      label: total ? `配置检查进行中（${counts}）` : '配置检查进行中',
      tone: 'info',
      showLiveHint: true,
    }
  }
  if (total === 0) {
    return {
      kind: 'none',
      configured: 0,
      total: 0,
      label: '配置清单为空',
      tone: 'muted',
      showLiveHint: false,
    }
  }
  if (configured === total) {
    return {
      kind: 'all',
      configured,
      total,
      label: `Skill 已全部配置完（${counts}）`,
      tone: 'ok',
      showLiveHint: false,
    }
  }
  if (input.lastCheckOk === false) {
    return {
      kind: 'failed',
      configured,
      total,
      label: configured > 0 ? `上次检查失败（${counts} 已配置）` : '上次检查失败',
      tone: 'err',
      showLiveHint: false,
    }
  }
  if (configured > 0) {
    return {
      kind: 'partial',
      configured,
      total,
      label: `部分已配置（${counts}）`,
      tone: 'warn',
      showLiveHint: false,
    }
  }
  return {
    kind: 'none',
    configured,
    total,
    label: '尚未完成 Skill 配置',
    tone: 'muted',
    showLiveHint: false,
  }
}
