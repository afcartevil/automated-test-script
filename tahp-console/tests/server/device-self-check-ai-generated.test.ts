import { describe, expect, it } from 'vitest'
import {
  getAllCaseCatalogs,
  getCaseCatalogDetail,
  initDeviceSelfCheck,
} from '../../packages/server/src/services/tahp/device-self-check'

describe('device self-check ai_generated catalog', () => {
  it('always exposes ai_generated group even without cases', () => {
    initDeviceSelfCheck()

    const aiGroup = getAllCaseCatalogs().find(group => group.testType === 'ai_generated')
    expect(aiGroup?.label).toBe('AI用例')
    expect(aiGroup?.modules).toHaveLength(1)
    expect(aiGroup?.modules[0]?.module).toBe('generated')

    const detail = getCaseCatalogDetail('ai_generated')
    expect(Array.isArray(detail)).toBe(true)
  })
})
