import type { AdaptLayoutFieldDef } from './types'

const FIELD_NAME_RE = /^[a-zA-Z][a-zA-Z0-9_]*$/

export function validateLayoutFields(fields: unknown): AdaptLayoutFieldDef[] {
  if (!Array.isArray(fields) || fields.length === 0) {
    throw new Error('fields 必须是非空数组')
  }
  const names = new Set<string>()
  const result: AdaptLayoutFieldDef[] = []

  for (const raw of fields) {
    if (!raw || typeof raw !== 'object') throw new Error('字段定义无效')
    const f = raw as Record<string, unknown>
    const name = String(f.name || '').trim()
    const label = String(f.label || '').trim()
    const type = String(f.type || 'text').trim() as AdaptLayoutFieldDef['type']

    if (!FIELD_NAME_RE.test(name)) {
      throw new Error(`字段名 "${name}" 无效，须以字母开头且仅含字母数字下划线`)
    }
    if (!label) throw new Error(`字段 "${name}" 缺少 label`)
    if (!['text', 'select', 'textarea'].includes(type)) {
      throw new Error(`字段 "${name}" 类型无效: ${type}`)
    }
    if (names.has(name)) throw new Error(`字段名重复: ${name}`)
    names.add(name)

    const item: AdaptLayoutFieldDef = {
      name,
      label,
      type,
      required: f.required === true,
      placeholder: typeof f.placeholder === 'string' ? f.placeholder : undefined,
    }

    if (type === 'select') {
      const opts = Array.isArray(f.options) ? f.options : []
      item.options = opts.map((o: unknown) => {
        const opt = o as Record<string, unknown>
        return {
          label: String(opt.label ?? opt.value ?? ''),
          value: String(opt.value ?? opt.label ?? ''),
        }
      }).filter(o => o.label && o.value)
      if (!item.options.length) {
        throw new Error(`下拉字段 "${name}" 至少需要一个选项`)
      }
    }

    result.push(item)
  }

  return result
}

const SKILL_ID_RE = /^[\w][\w.-]*$/

export function validateRelatedSkills(skills: unknown): string[] {
  if (!Array.isArray(skills)) {
    throw new Error('related_skills 必须是数组')
  }
  const result: string[] = []
  const seen = new Set<string>()
  for (const raw of skills) {
    const id = String(raw ?? '').trim()
    if (!id) continue
    if (!SKILL_ID_RE.test(id)) {
      throw new Error(`Skill ID "${id}" 格式无效`)
    }
    if (seen.has(id)) continue
    seen.add(id)
    result.push(id)
  }
  if (!result.length) {
    throw new Error('至少保留一个关联 Skill')
  }
  return result
}
