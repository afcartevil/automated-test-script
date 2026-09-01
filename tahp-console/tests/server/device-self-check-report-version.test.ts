import { afterEach, describe, expect, it, vi } from 'vitest'
import { EventEmitter } from 'events'
import {
  __testingOtaVersionProp,
  __testingResolveReportOtaVersion,
  type TestSession,
} from '../../packages/server/src/services/tahp/device-self-check'

const spawnMock = vi.fn()

vi.mock('child_process', async (importOriginal) => {
  const actual = await importOriginal<typeof import('child_process')>()
  return {
    ...actual,
    spawn: (...args: unknown[]) => spawnMock(...args),
  }
})

function mockGetprop(stdout: string) {
  spawnMock.mockImplementation(() => {
    const proc = new EventEmitter() as EventEmitter & {
      stdout?: EventEmitter
      stderr?: EventEmitter
      killed: boolean
      kill: () => void
    }
    proc.stdout = new EventEmitter()
    proc.stderr = new EventEmitter()
    proc.killed = false
    proc.kill = () => {
      proc.killed = true
    }
    queueMicrotask(() => {
      if (stdout) proc.stdout?.emit('data', Buffer.from(stdout))
      proc.emit('close', 0)
    })
    return proc
  })
}

function makeSession(otaVersion?: string): TestSession {
  return {
    deviceId: 'ut-ota-1',
    testType: 'smoke',
    modules: ['usd'],
    currentModuleIndex: 0,
    moduleProgress: {},
    caseResults: {},
    isRunning: false,
    auxiliaryDevices: [],
    otaVersion,
  }
}

describe('device-self-check report OTA version', () => {
  afterEach(() => {
    spawnMock.mockReset()
    vi.clearAllMocks()
  })

  it('uses persist.sys.ota_version from adb', async () => {
    mockGetprop('X6885O6-15.1.2.001\n')
    const session = makeSession()
    const version = await __testingResolveReportOtaVersion('ut-ota-1', session)
    expect(version).toBe('X6885O6-15.1.2.001')
    expect(session.otaVersion).toBe('X6885O6-15.1.2.001')
    const args = spawnMock.mock.calls[0]?.[1] as string[] | undefined
    expect(args).toContain(__testingOtaVersionProp)
  })

  it('falls back to session cache when adb returns empty', async () => {
    mockGetprop('')
    const session = makeSession('cached-ota-v1')
    const version = await __testingResolveReportOtaVersion('ut-ota-1', session)
    expect(version).toBe('cached-ota-v1')
  })
})
