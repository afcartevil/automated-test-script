export type ConfigTab = 'models' | 'skills' | 'form' | 'batch'

export const CONFIG_ROUTE_NAME = 'tahp.config'

/** 一键配置表单页「启动」按钮文案 */
export const SKILL_CONFIG_CHECK_BUTTON_LABEL = '启动skill配置检查'

/** 一键配置表单页合并按钮：先保存再启动检查 */
export const SAVE_AND_START_SKILL_CHECK_LABEL = '保存并启动skill配置检查'

export const CONFIG_TAB_LABELS: Record<ConfigTab, string> = {
  models: '模型管理',
  skills: '常用 Skill 配置',
  form: '一键配置表单',
  batch: 'Skill 配置检查',
}

/** 配置页可见的主 Tab（不含 batch 子界面） */
export const CONFIG_MAIN_TABS: ConfigTab[] = ['models', 'skills', 'form']

export function parseConfigTab(raw: unknown): ConfigTab {
  if (raw === 'skills' || raw === 'form' || raw === 'batch') return raw
  return 'models'
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
