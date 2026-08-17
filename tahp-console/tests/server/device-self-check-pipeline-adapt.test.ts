import { describe, expect, it } from 'vitest'
import {
  getAllCaseCatalogs,
  getCaseCatalogDetail,
  initDeviceSelfCheck,
} from '../../packages/server/src/services/tahp/device-self-check'

describe('device self-check pipeline_adapt catalog', () => {
  it('loads pipeline_adapt TP and vibrator catalog modules', () => {
    initDeviceSelfCheck()

    const group = getAllCaseCatalogs().find(g => g.testType === 'pipeline_adapt')
    expect(group?.label).toBe('流水线适配自动化测试')
    expect(group?.modules.map(m => m.module)).toEqual(['tp', 'vibrator'])
    expect(group?.modules[0]).toMatchObject({
      module: 'tp',
      moduleLabel: 'TP',
    })
    expect(group?.modules[0]?.cases).toHaveLength(1)
    expect(group?.modules[0]?.cases[0]?.caseName).toBe('TP适配检查')
    expect(group?.modules[1]).toMatchObject({
      module: 'vibrator',
      moduleLabel: '马达',
    })
    expect(group?.modules[1]?.cases).toHaveLength(1)
    expect(group?.modules[1]?.cases[0]?.caseName).toBe('马达适配检查')

    const detail = getCaseCatalogDetail('pipeline_adapt')
    expect(detail).toHaveLength(2)
    expect(detail[0]).toMatchObject({
      testType: 'pipeline_adapt',
      module: 'tp',
      moduleLabel: 'TP',
      caseName: 'TP适配检查',
      automationMode: 'full',
    })
    expect(detail[1]).toMatchObject({
      testType: 'pipeline_adapt',
      module: 'vibrator',
      moduleLabel: '马达',
      caseName: '马达适配检查',
      automationMode: 'full',
    })
    expect(typeof detail[0]?.preconditions).toBe('string')
    expect(typeof detail[0]?.manualSteps).toBe('string')
    expect(typeof detail[0]?.expectedResult).toBe('string')
    expect(typeof detail[1]?.preconditions).toBe('string')
    expect(typeof detail[1]?.manualSteps).toBe('string')
    expect(typeof detail[1]?.expectedResult).toBe('string')
  })
})
