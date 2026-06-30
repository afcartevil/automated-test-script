import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { existsSync, mkdtempSync, rmSync } from 'fs'
import { join } from 'path'
import { tmpdir } from 'os'
import {
  buildScheduleKey,
  markPlanExecutionNoDevice,
  markPlanExecutionRunning,
} from '../../packages/server/src/services/tahp/test-plan-executions'
import {
  saveTestPlanRules,
  syncProjectNodesFromXlsx,
  toDisplayDate,
} from '../../packages/server/src/services/tahp/test-planning'

const startTestMock = vi.fn()
const snapshotDevicesMock = vi.fn()
const buildPlannedTestFlashPayloadMock = vi.fn()

vi.mock('../../packages/server/src/services/tahp/device-self-check', () => ({
  snapshotDevices: (...args: unknown[]) => snapshotDevicesMock(...args),
  startTest: (...args: unknown[]) => startTestMock(...args),
}))

vi.mock('../../packages/server/src/services/tahp/device-flash', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../packages/server/src/services/tahp/device-flash')>()
  return {
    ...actual,
    buildPlannedTestFlashPayload: (...args: unknown[]) =>
      buildPlannedTestFlashPayloadMock(...args),
  }
})

describe('test-plan-executor', () => {
  let tempDir = ''
  let xlsxPath = ''
  let nodeDate = ''
  let scheduleKey = ''

  beforeEach(async () => {
    tempDir = mkdtempSync(join(tmpdir(), 'tahp-plan-exec-'))
    process.env.TAHP_TEST_PLANNING_CONFIG_DIR = tempDir
    xlsxPath = join(tempDir, 'project-info.xlsx')

    const today = new Date()
    today.setHours(0, 0, 0, 0)
    nodeDate = toDisplayDate(today)
    scheduleKey = buildScheduleKey('X6876', 'STR4A', nodeDate, 'monkey')

    const XLSX = await import('xlsx')
    const rows = [
      ['项目名称', '是否已完成升级', 'STR4', 'STR4A', 'STR 5', 'STR6'],
      ['X6876', '升级中', '2026-05-25', nodeDate, '2026/07/27', ''],
    ]
    const workbook = XLSX.utils.book_new()
    const sheet = XLSX.utils.aoa_to_sheet(rows)
    XLSX.utils.book_append_sheet(workbook, sheet, '项目信息')
    XLSX.writeFile(workbook, xlsxPath)

    await syncProjectNodesFromXlsx(xlsxPath)
    await saveTestPlanRules([
      { node: 'STR4A', offsetDays: 0, testType: 'monkey' },
    ])

    startTestMock.mockReset()
    snapshotDevicesMock.mockReset()
    buildPlannedTestFlashPayloadMock.mockReset()
    buildPlannedTestFlashPayloadMock.mockResolvedValue({
      enabled: true,
      pkgPath: '\\\\server\\daily\\Open\\rom.zip',
      stageVersion: 'Open',
      rootPkgPath: '\\\\server\\daily\\Root\\root.zip',
    })
    vi.resetModules()
  })

  afterEach(() => {
    delete process.env.TAHP_TEST_PLANNING_CONFIG_DIR
    if (tempDir && existsSync(tempDir)) rmSync(tempDir, { recursive: true, force: true })
  })

  it('marks no_device when no matching idle device', async () => {
    snapshotDevicesMock.mockReturnValue([
      { deviceId: 'abc', deviceName: 'Other Phone', status: '空闲', role: '未分配' },
    ])
    startTestMock.mockResolvedValue(null)

    const { tickPlanExecutor } = await import('../../packages/server/src/services/tahp/test-plan-executor')
    await tickPlanExecutor()

    const { getPlanExecution } = await import('../../packages/server/src/services/tahp/test-plan-executions')
    const record = await getPlanExecution(scheduleKey)
    expect(record?.runtimeStatus).toBe('no_device')
    expect(buildPlannedTestFlashPayloadMock).not.toHaveBeenCalled()
    expect(startTestMock).not.toHaveBeenCalled()
  })

  it('auto-starts monkey test with flash payload including root package', async () => {
    snapshotDevicesMock.mockReturnValue([
      { deviceId: 'dev-1', deviceName: 'Infinix X6876', status: '空闲', role: '未分配' },
    ])
    startTestMock.mockResolvedValue({ device: { deviceId: 'dev-1' }, session: {} })

    const { tickPlanExecutor } = await import('../../packages/server/src/services/tahp/test-plan-executor')
    await tickPlanExecutor()

    expect(buildPlannedTestFlashPayloadMock).toHaveBeenCalledWith('dev-1', 'monkey')
    expect(startTestMock).toHaveBeenCalledWith(
      'dev-1',
      'monkey',
      {
        enabled: true,
        pkgPath: '\\\\server\\daily\\Open\\rom.zip',
        stageVersion: 'Open',
        rootPkgPath: '\\\\server\\daily\\Root\\root.zip',
      },
      expect.objectContaining({ scheduleKey }),
    )

    const { getPlanExecution } = await import('../../packages/server/src/services/tahp/test-plan-executions')
    const record = await getPlanExecution(scheduleKey)
    expect(record?.runtimeStatus).toBe('running')
    expect(record?.deviceId).toBe('dev-1')
  })

  it('auto-starts str4 test with flash payload without root package', async () => {
    const str4Key = buildScheduleKey('X6876', 'STR4A', nodeDate, 'str4')
    await saveTestPlanRules([
      { node: 'STR4A', offsetDays: 0, testType: 'str4' },
    ])
    buildPlannedTestFlashPayloadMock.mockResolvedValue({
      enabled: true,
      pkgPath: '\\\\server\\daily\\Open\\rom.zip',
      stageVersion: 'Open',
    })

    snapshotDevicesMock.mockReturnValue([
      { deviceId: 'dev-1', deviceName: 'Infinix X6876', status: '空闲', role: '未分配' },
    ])
    startTestMock.mockResolvedValue({ device: { deviceId: 'dev-1' }, session: {} })

    const { tickPlanExecutor } = await import('../../packages/server/src/services/tahp/test-plan-executor')
    await tickPlanExecutor()

    expect(buildPlannedTestFlashPayloadMock).toHaveBeenCalledWith('dev-1', 'str4')
    expect(startTestMock).toHaveBeenCalledWith(
      'dev-1',
      'str4',
      {
        enabled: true,
        pkgPath: '\\\\server\\daily\\Open\\rom.zip',
        stageVersion: 'Open',
      },
      expect.objectContaining({ scheduleKey: str4Key }),
    )
  })

  it('marks no_device when flash package resolution fails', async () => {
    snapshotDevicesMock.mockReturnValue([
      { deviceId: 'dev-1', deviceName: 'Infinix X6876', status: '空闲', role: '未分配' },
    ])
    buildPlannedTestFlashPayloadMock.mockRejectedValue(new Error('DEV 路径不存在'))

    const { tickPlanExecutor } = await import('../../packages/server/src/services/tahp/test-plan-executor')
    await tickPlanExecutor()

    expect(startTestMock).not.toHaveBeenCalled()
    const { getPlanExecution } = await import('../../packages/server/src/services/tahp/test-plan-executions')
    const record = await getPlanExecution(scheduleKey)
    expect(record?.runtimeStatus).toBe('no_device')
  })

  it('persists running state via markPlanExecutionRunning', async () => {
    await markPlanExecutionRunning(scheduleKey, 'dev-1')
    await markPlanExecutionNoDevice(scheduleKey)
    const { getPlanExecution } = await import('../../packages/server/src/services/tahp/test-plan-executions')
    expect((await getPlanExecution(scheduleKey))?.runtimeStatus).toBe('no_device')
  })
})
