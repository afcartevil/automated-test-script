import { describe, expect, it } from 'vitest'
import { validateLayoutFields, validateRelatedSkills } from '../../packages/server/src/services/tahp/adapt-layout/validate'
import { resolveFormFieldLabels } from '../../packages/server/src/services/tahp/adapt-layout/service'

describe('adapt-layout validate', () => {
  it('accepts valid field definitions', () => {
    const fields = validateLayoutFields([
      { name: 'ic_model', label: 'IC型号', type: 'text', required: true },
      {
        name: 'ic_vendor',
        label: 'IC厂商',
        type: 'select',
        required: true,
        options: [{ label: 'GOODIX', value: 'goodix' }],
      },
    ])
    expect(fields).toHaveLength(2)
    expect(fields[1].options?.[0].value).toBe('goodix')
  })

  it('rejects duplicate field names', () => {
    expect(() => validateLayoutFields([
      { name: 'foo', label: 'A', type: 'text', required: false },
      { name: 'foo', label: 'B', type: 'text', required: false },
    ])).toThrow(/重复/)
  })
})

describe('adapt-layout related_skills', () => {
  it('accepts valid skill id list and dedupes', () => {
    const skills = validateRelatedSkills(['drv-fp-adapt', 'drv-fp-check', 'drv-fp-adapt'])
    expect(skills).toEqual(['drv-fp-adapt', 'drv-fp-check'])
  })

  it('rejects empty skill list', () => {
    expect(() => validateRelatedSkills([])).toThrow(/至少保留/)
  })
})

describe('resolveFormFieldLabels', () => {
  it('uses form field labels and preserves order', () => {
    const rows = resolveFormFieldLabels(
      { prj_path: 'D:\\test', user_notes: '' },
      [
        { name: 'prj_path', label: '项目路径' },
        { name: 'user_notes', label: '补充说明' },
      ],
    )
    expect(rows).toEqual([{ name: 'prj_path', label: '项目路径', value: 'D:\\test' }])
  })
})
