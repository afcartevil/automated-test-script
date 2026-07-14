/** ECC 配置域：三平台代码仓路径至少填一项；号码/有卡等可多组临时填写 */

export const ECC_REPO_PATH_FIELDS = [
  'repo_path_mtk',
  'repo_path_unisoc',
  'repo_path_qualcomm',
] as const

/** 一组 ECC 条目字段（UI 可复制多组，不落盘） */
export const ECC_ENTRY_FIELD_NAMES = [
  'number',
  'with_sim',
  'without_sim',
  'display_name',
  'block',
] as const

export type EccEntryFieldName = (typeof ECC_ENTRY_FIELD_NAMES)[number]

export interface EccEntryFormRow {
  number: string
  with_sim: string
  without_sim: string
  display_name: string
  block: string
}

export const ECC_ENTRY_FIELD_META: Array<{
  name: EccEntryFieldName
  label: string
  type: 'text' | 'select'
  placeholder?: string
  options?: Array<{ label: string; value: string }>
}> = [
  {
    name: 'number',
    label: '号码',
    type: 'text',
    placeholder: '紧急号码（选填）',
  },
  {
    name: 'with_sim',
    label: '有卡情况',
    type: 'select',
    placeholder: '不选表示不更改',
    options: [
      { label: '真紧急', value: '真紧急' },
      { label: '假紧急', value: '假紧急' },
      { label: '非紧急', value: '非紧急' },
    ],
  },
  {
    name: 'without_sim',
    label: '无卡情况',
    type: 'select',
    placeholder: '不选表示不更改',
    options: [
      { label: '是紧急号码', value: '真紧急' },
      { label: '不是紧急号码', value: '非紧急' },
    ],
  },
  {
    name: 'display_name',
    label: '名称',
    type: 'text',
    placeholder: '号码显示名称',
  },
  {
    name: 'block',
    label: '是否需要屏蔽',
    type: 'select',
    placeholder: '仅 MTK 生效',
    options: [
      { label: '是', value: 'yes' },
      { label: '否', value: 'no' },
    ],
  },
]

export function createEmptyEccEntry(): EccEntryFormRow {
  return {
    number: '',
    with_sim: '',
    without_sim: '',
    display_name: '',
    block: '',
  }
}

export function isEccEntryFieldName(name: string): boolean {
  return (ECC_ENTRY_FIELD_NAMES as readonly string[]).includes(name)
}

export function hasEccRepoPath(formData: Record<string, string | undefined>): boolean {
  return ECC_REPO_PATH_FIELDS.some((k) => (formData[k] || '').trim().length > 0)
}

export function isEccConfigFormComplete(formData: Record<string, string | undefined>): boolean {
  return hasEccRepoPath(formData)
}

/** 打包多组 ECC 条目为 Agent 表单参数（临时 UI 状态） */
export function packEccEntriesForAgent(entries: EccEntryFormRow[]): {
  formData: Record<string, string>
  formFields: Array<{ name: string; label: string; required: boolean }>
} {
  const formData: Record<string, string> = {}
  const formFields: Array<{ name: string; label: string; required: boolean }> = []

  entries.forEach((entry, idx) => {
    const n = idx + 1
    for (const meta of ECC_ENTRY_FIELD_META) {
      const name = `ecc_group_${n}_${meta.name}`
      formData[name] = entry[meta.name] || ''
      formFields.push({
        name,
        label: `ECC组${n} · ${meta.label}`,
        required: false,
      })
    }
  })

  formData.ecc_entry_count = String(entries.length)
  formData.ecc_entries_json = JSON.stringify(entries)
  formFields.push(
    { name: 'ecc_entry_count', label: 'ECC配置组数', required: false },
    { name: 'ecc_entries_json', label: 'ECC配置条目JSON（多组）', required: false },
  )

  return { formData, formFields }
}
