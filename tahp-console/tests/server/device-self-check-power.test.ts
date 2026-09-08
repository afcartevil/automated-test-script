import { describe, expect, it } from 'vitest'
import { spawnSync } from 'child_process'
import { join } from 'path'
import { existsSync, readFileSync } from 'fs'
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
      '通用全域测试',
      '基础场景',
      '待机',
      'DOU',
      'PFMMod',
    ])

    const detail = getCaseCatalogDetail('power')
    expect(detail).toHaveLength(5)
    expect(detail.map(item => item.caseName)).toEqual([
      '通用全域测试',
      '基础场景',
      '待机',
      'DOU',
      'PFMMod',
    ])
    expect(detail[0]).toMatchObject({
      testType: 'power',
      module: 'current_analysis',
      moduleLabel: '场景功耗测量',
      caseName: '通用全域测试',
      key: 'power/current_analysis/1',
    })
    expect(detail[0]?.preconditions).toContain('SSID:power_cloud')
    expect(detail[0]?.preconditions).toContain('PSW:1234567809')
    expect(detail[2]?.caseName).toBe('待机')
    expect(detail[3]?.preconditions).toContain('暂不实现')
    expect(detail[4]?.preconditions).toContain('已支持')
    expect(detail[4]?.preconditions).toContain('SSID:power_cloud')
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

  it('maps power UI scenes to standby/base/full scheduler modes in task_proc', () => {
    const taskProc = join(
      tahpPaths.projectRoot,
      'tahp-console/packages/server/src/services/tahp/self-check/python/tools/tpower_auto/tests/current_analysis/task_proc.py',
    )
    const src = readFileSync(taskProc, 'utf-8')
    expect(src).toContain('def resolve_power_scene_mode')
    expect(src).toContain('("复杂待机", "待机")')
    expect(src).toContain('return "standby"')
    expect(src).toContain('text == "基础场景"')
    expect(src).toContain('return "base"')
    expect(src).toContain('通用全域测试')
    expect(src).toContain('return "full"')
    expect(src).toContain('return "unsupported"')
    expect(src).toContain('"PFMMod"')
    expect(src).toContain('text == "DOU"')
    expect(src).toContain('场景模式=待机')
    expect(src).toContain('场景模式=基础场景')
    expect(src).toContain('执行全量调度')
    expect(src).toContain('暂不实现')
    expect(src).toContain('scene_finished')

    const phoneConfig = join(
      tahpPaths.projectRoot,
      'tahp-console/packages/server/src/services/tahp/self-check/python/tools/tpower_auto/tests/current_analysis/phoneconfig.py',
    )
    expect(readFileSync(phoneConfig, 'utf-8')).toContain('check_device_to_link_wifi(self.u2d, "power_cloud", "1234567809")')

    expect(readFileSync(join(
      tahpPaths.projectRoot,
      'tahp-console/packages/server/src/services/tahp/self-check/python/cases/power/current_analysis/case1.py',
    ), 'utf-8')).toContain('通用全域测试')
    expect(readFileSync(join(
      tahpPaths.projectRoot,
      'tahp-console/packages/server/src/services/tahp/self-check/python/cases/power/current_analysis/case3.py',
    ), 'utf-8')).toContain('待机')
    expect(readFileSync(join(
      tahpPaths.projectRoot,
      'tahp-console/packages/server/src/services/tahp/self-check/python/cases/power/current_analysis/case4.py',
    ), 'utf-8')).toContain('DOU 暂不实现')
    expect(readFileSync(join(
      tahpPaths.projectRoot,
      'tahp-console/packages/server/src/services/tahp/self-check/python/cases/power/current_analysis/case5.py',
    ), 'utf-8')).toContain('PFMMod')
    expect(readFileSync(join(
      tahpPaths.projectRoot,
      'tahp-console/packages/server/src/services/tahp/self-check/python/cases/power/current_analysis/case5.py',
    ), 'utf-8')).not.toContain('暂不实现')
  })
})
