import { describe, expect, it } from 'vitest'
import {
  getAllCaseCatalogs,
  getCaseCatalogDetail,
  getSettings,
  initDeviceSelfCheck,
} from '../../packages/server/src/services/tahp/device-self-check'
import { resolvePythonSpawn, tahpPaths } from '../../packages/server/src/services/tahp/paths'
import { spawnSync } from 'child_process'

describe('device self-check monkey catalog', () => {
  it('loads monkey test catalog and default duration', () => {
    initDeviceSelfCheck()

    const monkeyGroup = getAllCaseCatalogs().find(group => group.testType === 'monkey')
    expect(monkeyGroup?.label).toBe('monkey测试')
    expect(monkeyGroup?.modules).toHaveLength(1)
    expect(monkeyGroup?.modules[0]?.module).toBe('monkey')
    expect(monkeyGroup?.modules[0]?.cases[0]?.caseName).toBe('monkey测试')

    const detail = getCaseCatalogDetail('monkey')
    expect(detail).toHaveLength(1)
    expect(detail[0]).toMatchObject({
      testType: 'monkey',
      module: 'monkey',
      moduleLabel: 'monkey测试',
      caseName: 'monkey测试',
      preconditions: '',
      manualSteps: '',
      expectedResult: '',
    })
    expect(getSettings().monkeyDuration).toBeTruthy()
  })

  it('resolves Python 3 for self-check subprocesses on Windows', () => {
    const { command, prefixArgs } = resolvePythonSpawn()
    expect(command).toBeTruthy()

    const result = spawnSync(command, [...prefixArgs, '--version'], {
      encoding: 'utf-8',
      windowsHide: true,
    })
    const version = `${result.stdout || ''}${result.stderr || ''}`.trim()
    expect(result.status).toBe(0)
    expect(version).toMatch(/Python 3\./)
    expect(tahpPaths.python).toMatch(/py|python/i)
  })
})
