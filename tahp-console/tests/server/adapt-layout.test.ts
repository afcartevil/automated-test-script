import { describe, expect, it } from 'vitest'
import { validateLayoutFields, validateRelatedSkills } from '../../packages/server/src/services/tahp/adapt-layout/validate'
import { resolveFormFieldLabels } from '../../packages/server/src/services/tahp/adapt-layout/service'
import {
  fingerprintLayout,
  isLocalDirty,
  mergePublishedIntoLocal,
} from '../../packages/server/src/services/tahp/adapt-layout/merge'
import type { AdaptDomainLayoutRecord, AdaptLayoutManifest } from '../../packages/server/src/services/tahp/adapt-layout/types'

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

  it('accepts checklist field with defaultValue', () => {
    const fields = validateLayoutFields([
      {
        name: 'feature_checklist',
        label: '特性清单',
        type: 'checklist',
        required: false,
        defaultValue: '智能触控采样率\tSF-202507-008773',
      },
    ])
    expect(fields[0].type).toBe('checklist')
    expect(fields[0].defaultValue).toContain('SF-202507-008773')
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

function localManifest(layouts: Record<string, AdaptDomainLayoutRecord>): AdaptLayoutManifest {
  return {
    schema_version: 1,
    layouts,
    sync: { cloud_sync_enabled: true },
  }
}

function tpRecord(overrides: Partial<AdaptDomainLayoutRecord> = {}): AdaptDomainLayoutRecord {
  const fields = overrides.fields ?? [{ name: 'ic_model', label: 'IC型号', type: 'text' as const, required: true }]
  const related = overrides.related_skills ?? ['tp-adapt-bringup']
  return {
    schema_version: 1,
    domain_id: 'tp',
    fields,
    related_skills: related,
    revision: 1,
    updated_at: '2026-08-24T00:00:00.000Z',
    source: 'user',
    ...overrides,
  }
}

describe('adapt-layout merge', () => {
  it('treats user source without published fingerprint as dirty', () => {
    expect(isLocalDirty(tpRecord())).toBe(true)
    expect(isLocalDirty(tpRecord({
      source: 'cloud',
      published_fingerprint: fingerprintLayout(
        [{ name: 'ic_model', label: 'IC型号', type: 'text', required: true }],
        ['tp-adapt-bringup'],
      ),
    }))).toBe(false)
  })

  it('applies published layout when local has no override', () => {
    const { merged, updatedDomains, skippedDirtyDomains } = mergePublishedIntoLocal(
      localManifest({}),
      {
        workspace_id: 'adapt-debug',
        layouts: {
          tp: {
            schema_version: 1,
            domain_id: 'tp',
            fields: [{ name: 'debug_project', label: '调试项目名', type: 'text', required: true }],
            related_skills: ['tp-adapt-bringup'],
            revision: 4,
            updated_at: '2026-08-24T10:00:00.000Z',
          },
        },
      },
    )
    expect(updatedDomains).toEqual(['tp'])
    expect(skippedDirtyDomains).toEqual([])
    expect(merged.layouts.tp.source).toBe('cloud')
    expect(merged.layouts.tp.published_revision).toBe(4)
  })

  it('overwrites dirty local module with published layout', () => {
    const localTp = tpRecord({
      source: 'user',
      published_revision: 3,
      published_fingerprint: fingerprintLayout(
        [{ name: 'ic_model', label: 'IC型号', type: 'text', required: true }],
        ['tp-adapt-bringup'],
      ),
      fields: [{ name: 'ic_model', label: 'IC型号-本地改', type: 'text', required: true }],
    })
    const { updatedDomains, skippedDirtyDomains, merged } = mergePublishedIntoLocal(
      localManifest({ tp: localTp }),
      {
        workspace_id: 'adapt-debug',
        layouts: {
          tp: {
            schema_version: 1,
            domain_id: 'tp',
            fields: [{ name: 'vendor', label: '厂商', type: 'text', required: false }],
            related_skills: ['tp-adapt-bringup'],
            revision: 4,
            updated_at: '2026-08-24T10:00:00.000Z',
          },
        },
      },
    )
    expect(skippedDirtyDomains).toEqual([])
    expect(updatedDomains).toEqual(['tp'])
    expect(merged.layouts.tp.fields[0].name).toBe('vendor')
    expect(merged.layouts.tp.source).toBe('cloud')
    expect(merged.layouts.tp.published_revision).toBe(4)
  })

  it('applies published when local dirty content already matches remote', () => {
    const fields = [{ name: 'ic_model', label: 'IC型号', type: 'text' as const, required: true }]
    const localTp = tpRecord({
      source: 'user',
      fields,
      published_revision: 3,
      published_fingerprint: 'old',
    })
    const { updatedDomains, skippedDirtyDomains, merged } = mergePublishedIntoLocal(
      localManifest({ tp: localTp }),
      {
        workspace_id: 'adapt-debug',
        layouts: {
          tp: {
            schema_version: 1,
            domain_id: 'tp',
            fields,
            related_skills: ['tp-adapt-bringup'],
            revision: 4,
            updated_at: '2026-08-24T10:00:00.000Z',
          },
        },
      },
    )
    expect(skippedDirtyDomains).toEqual([])
    expect(updatedDomains).toEqual(['tp'])
    expect(merged.layouts.tp.source).toBe('cloud')
    expect(merged.layouts.tp.published_revision).toBe(4)
  })

  it('overwrites all published modules including locally dirty ones', () => {
    const dirtyTp = tpRecord({
      source: 'user',
      fields: [{ name: 'local_only', label: '本地', type: 'text', required: false }],
    })
    const { updatedDomains, skippedDirtyDomains, merged } = mergePublishedIntoLocal(
      localManifest({ tp: dirtyTp }),
      {
        workspace_id: 'adapt-debug',
        layouts: {
          tp: {
            schema_version: 1,
            domain_id: 'tp',
            fields: [{ name: 'remote', label: '远端', type: 'text', required: false }],
            related_skills: ['tp-adapt-bringup'],
            revision: 2,
            updated_at: '2026-08-24T10:00:00.000Z',
          },
          lcm: {
            schema_version: 1,
            domain_id: 'lcm',
            fields: [{ name: 'panel', label: '屏', type: 'text', required: true }],
            related_skills: ['display_analyser'],
            revision: 1,
            updated_at: '2026-08-24T10:00:00.000Z',
          },
        },
      },
    )
    expect(skippedDirtyDomains).toEqual([])
    expect(updatedDomains).toEqual(['tp', 'lcm'])
    expect(merged.layouts.lcm.fields[0].name).toBe('panel')
    expect(merged.layouts.tp.fields[0].name).toBe('remote')
    expect(merged.layouts.tp.source).toBe('cloud')
  })
})
