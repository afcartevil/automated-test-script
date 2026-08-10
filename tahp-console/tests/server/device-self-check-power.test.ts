import { describe, expect, it } from 'vitest'
import { spawnSync } from 'child_process'
import { join } from 'path'
import { existsSync } from 'fs'
import {
  getAllCaseCatalogs,
  getCaseCatalogDetail,
  initDeviceSelfCheck,
} from '../../packages/server/src/services/tahp/device-self-check'
import { tahpPaths } from '../../packages/server/src/services/tahp/paths'
import { resolvePythonCommand } from '../../scripts/lib/tahp-paths.mjs'

describe('device self-check power catalog', () => {
  it('loads power test catalog and tool assets', () => {
    initDeviceSelfCheck()

    const powerGroup = getAllCaseCatalogs().find(group => group.testType === 'power')
    expect(powerGroup?.label).toBe('功耗自动化测试')
    expect(powerGroup?.modules).toHaveLength(1)
    expect(powerGroup?.modules[0]?.module).toBe('current_analysis')
    expect(powerGroup?.modules[0]?.moduleLabel).toBe('场景功耗测量')
    expect(powerGroup?.modules[0]?.cases.map(item => item.caseName)).toEqual([
      '复杂待机',
      '基础场景',
      'DOU',
      'PFMMod',
    ])

    const detail = getCaseCatalogDetail('power')
    expect(detail).toHaveLength(4)
    expect(detail.map(item => item.caseName)).toEqual([
      '复杂待机',
      '基础场景',
      'DOU',
      'PFMMod',
    ])
    expect(detail[0]).toMatchObject({
      testType: 'power',
      module: 'current_analysis',
      moduleLabel: '场景功耗测量',
      caseName: '复杂待机',
      key: 'power/current_analysis/1',
    })
    expect(detail[0]?.manualSteps).toContain('TPower')

    const runner = join(
      tahpPaths.projectRoot,
      'tahp-console/packages/server/src/services/tahp/self-check/python/tools/tpower_auto/run_power_env.py',
    )
    expect(existsSync(runner)).toBe(true)
  })

  it('exposes summarize-xlsx command for report aggregation', () => {
    const runner = join(
      tahpPaths.projectRoot,
      'tahp-console/packages/server/src/services/tahp/self-check/python/tools/tpower_auto/run_power_env.py',
    )
    const { command, prefixArgs } = resolvePythonCommand()
    const result = spawnSync(command, [...prefixArgs, runner, 'summarize-xlsx'], {
      cwd: join(runner, '..'),
      encoding: 'utf-8',
    })
    expect(result.status).toBe(1)
    const payload = JSON.parse((result.stdout || '').trim().split('\n').pop() || '{}')
    expect(payload).toMatchObject({
      total: 0,
      message: expect.stringContaining('xlsx'),
    })
  })
})
