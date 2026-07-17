import { EventEmitter } from 'events'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('child_process', async (importOriginal) => {
  const actual = await importOriginal<typeof import('child_process')>()

  function mockSpawn(cmd: string, args: string[] = []) {
    const proc = new EventEmitter() as EventEmitter & {
      stdout: EventEmitter
      stderr: EventEmitter
      killed: boolean
      kill: () => boolean
    }
    proc.stdout = new EventEmitter()
    proc.stderr = new EventEmitter()
    proc.killed = false
    proc.kill = () => {
      proc.killed = true
      return true
    }

    const joined = args.join(' ')
    queueMicrotask(() => {
      let stdout = ''
      if (cmd === 'adb' && args[0] === 'devices') {
        stdout = 'List of devices attached\ndut-1\tdevice\n'
      } else if (joined.includes('getprop ro.product.model; getprop gsm.sim.state')) {
        stdout = 'Infinix X6876\nLOADED,ABSENT\n'
      } else if (joined.includes('getprop') && joined.includes('ro.product.model')) {
        stdout = 'Infinix X6876\n'
      } else if (joined.includes('getprop') && joined.includes('gsm.sim.state')) {
        stdout = 'LOADED,ABSENT\n'
      }
      proc.stdout.emit('data', Buffer.from(stdout))
      proc.emit('close', 0)
    })
    return proc
  }

  return {
    ...actual,
    spawn: vi.fn(mockSpawn),
  }
})

import {
  __testingResetDevices,
  __testingUpsertDevice,
  continueTest,
  countPresentSimCards,
  getDevice,
  refreshDeviceProbeInfo,
  refreshDevices,
  shouldRefreshSimOnListRefresh,
  type DeviceInfo,
  type TestSession,
} from '../../packages/server/src/services/tahp/device-self-check'

function emptySimCards(): DeviceInfo['simCards'] {
  return [
    { slotIndex: 0, operator: '', phoneNumber: '', present: false },
    { slotIndex: 1, operator: '', phoneNumber: '', present: false },
  ]
}

describe('device self-check SIM refresh', () => {
  beforeEach(() => {
    __testingResetDevices()
  })

  it('includes 不满足前置条件 in list-refresh SIM eligibility', () => {
    expect(shouldRefreshSimOnListRefresh('不满足前置条件')).toBe(true)
    expect(shouldRefreshSimOnListRefresh('空闲')).toBe(true)
    expect(shouldRefreshSimOnListRefresh('测试中')).toBe(false)
    expect(shouldRefreshSimOnListRefresh('等待测试开始')).toBe(false)
  })

  it('counts present SIM slots', () => {
    expect(countPresentSimCards(emptySimCards())).toBe(0)
    expect(countPresentSimCards([
      { slotIndex: 0, operator: '', phoneNumber: '', present: true },
      { slotIndex: 1, operator: '', phoneNumber: '', present: false },
    ])).toBe(1)
  })

  it('refreshDeviceProbeInfo overwrites stale SIM cache after card insert', async () => {
    __testingUpsertDevice({
      deviceId: 'dut-1',
      deviceName: 'dut-1',
      role: '测试机',
      status: '不满足前置条件',
      simCards: emptySimCards(),
      testDuration: 0,
      isMirroredResult: false,
      currentModule: 'tdd',
      testType: 'week',
    })

    expect(countPresentSimCards(getDevice('dut-1')?.simCards)).toBe(0)

    const updated = await refreshDeviceProbeInfo('dut-1')
    expect(updated).toBeTruthy()
    expect(updated?.deviceName).toBe('Infinix X6876')
    expect(countPresentSimCards(updated?.simCards)).toBe(1)
    expect(getDevice('dut-1')?.simCards[0]?.present).toBe(true)
  })

  it('refreshDevices re-probes SIM for 不满足前置条件 devices', async () => {
    __testingUpsertDevice({
      deviceId: 'dut-1',
      deviceName: 'stale-name',
      role: '测试机',
      status: '不满足前置条件',
      simCards: emptySimCards(),
      testDuration: 0,
      isMirroredResult: false,
      currentModule: 'tdd',
      testType: 'week',
    })

    const list = await refreshDevices()
    const dut = list.find(d => d.deviceId === 'dut-1')
    expect(dut?.status).toBe('不满足前置条件')
    expect(dut?.deviceName).toBe('Infinix X6876')
    expect(countPresentSimCards(dut?.simCards)).toBe(1)
  })

  it('continueTest refreshes SIM before resuming flow', async () => {
    const deviceId = 'dut-1'
    __testingUpsertDevice(
      {
        deviceId,
        deviceName: 'stale',
        role: '测试机',
        status: '不满足前置条件',
        simCards: emptySimCards(),
        testDuration: 0,
        isMirroredResult: false,
        currentModule: 'tdd',
        testType: 'week',
      },
      {
        deviceId,
        testType: 'custom',
        modules: [],
        currentModuleIndex: 0,
        moduleProgress: {},
        caseResults: {},
        isRunning: false,
        auxiliaryDevices: [],
      } satisfies TestSession,
    )

    const detail = await continueTest(deviceId)
    expect(detail).toBeTruthy()
    expect(countPresentSimCards(detail?.device.simCards)).toBe(1)
    expect(getDevice(deviceId)?.simCards[0]?.present).toBe(true)
  })
})
