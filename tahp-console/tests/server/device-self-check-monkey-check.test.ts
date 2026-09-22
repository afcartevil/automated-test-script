import { describe, expect, it } from 'vitest'
import {
  getAllCaseCatalogs,
  getCaseCatalogDetail,
  initDeviceSelfCheck,
} from '../../packages/server/src/services/tahp/device-self-check'

describe('device self-check monkey_check catalog', () => {
  it('loads monkey_check catalog with tne module', () => {
    initDeviceSelfCheck()

    const groups = getAllCaseCatalogs()
    const group = groups.find(g => g.testType === 'monkey_check')
    expect(group?.label).toBe('monkey结果检查')
    expect(group?.modules).toHaveLength(1)
    expect(group?.modules[0]?.module).toBe('tne')
    expect(group?.modules[0]?.moduleLabel).toBe('TNE异常检查')
    expect(group?.modules[0]?.cases[0]?.caseName).toBe('monkey结果检查')
    expect(group?.modules[0]?.cases[0]?.automationMode).toBe('full')

    // 排序：monkey_check 紧随 monkey 之后
    const order = groups.map(g => g.testType)
    expect(order.indexOf('monkey_check')).toBe(order.indexOf('monkey') + 1)
  })

  it('returns monkey_check catalog detail with preconditions and steps', () => {
    initDeviceSelfCheck()

    const detail = getCaseCatalogDetail('monkey_check')
    expect(detail).toHaveLength(1)
    expect(detail[0]).toMatchObject({
      testType: 'monkey_check',
      module: 'tne',
      moduleLabel: 'TNE异常检查',
      caseName: 'monkey结果检查',
    })
    expect(detail[0]?.preconditions).toContain('ADB')
    expect(detail[0]?.manualSteps).toContain('/data/TNE/0xffff')
    expect(detail[0]?.expectedResult).toContain('native crash')
  })
})
