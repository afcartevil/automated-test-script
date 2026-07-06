export type ConfigTab = 'models' | 'skills' | 'form' | 'batch'

export const CONFIG_ROUTE_NAME = 'tahp.config'

/** 一键配置表单页「启动」按钮文案 */
export const SKILL_CONFIG_CHECK_BUTTON_LABEL = '启动skill配置检查'

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
