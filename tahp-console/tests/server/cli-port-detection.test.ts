import { afterEach, describe, expect, it, vi } from 'vitest'

type ChildProcessMocks = {
  execFileSync: ReturnType<typeof vi.fn>
}

async function loadPortScan(overrides: Partial<ChildProcessMocks> = {}) {
  const execFileSync = overrides.execFileSync ?? vi.fn()

  vi.resetModules()
  vi.doMock('child_process', () => ({ execFileSync }))

  const mod = await import('../../scripts/lib/port-scan.mjs')
  return {
    ...mod,
    mocks: { execFileSync },
  }
}

describe('CLI port detection', () => {
  const originalPlatform = Object.getOwnPropertyDescriptor(process, 'platform')
  const originalSkip = process.env.TAHP_SKIP_PORT_SCAN
  const originalTimeout = process.env.TAHP_PORT_SCAN_TIMEOUT_MS

  afterEach(() => {
    vi.doUnmock('child_process')
    if (originalPlatform) {
      Object.defineProperty(process, 'platform', originalPlatform)
    }
    if (originalSkip === undefined) delete process.env.TAHP_SKIP_PORT_SCAN
    else process.env.TAHP_SKIP_PORT_SCAN = originalSkip
    if (originalTimeout === undefined) delete process.env.TAHP_PORT_SCAN_TIMEOUT_MS
    else process.env.TAHP_PORT_SCAN_TIMEOUT_MS = originalTimeout
  })

  it('falls back to lsof without executing ss when ss is unavailable', async () => {
    Object.defineProperty(process, 'platform', { value: 'darwin' })

    const execFileSync = vi.fn((command: string, args: string[]) => {
      if (command === 'sh' && args.at(-1) === 'ss') {
        throw new Error('not found')
      }
      if (command === 'sh' && args.at(-1) === 'lsof') {
        return ''
      }
      if (command === 'lsof') {
        return '1234\n1234\n'
      }
      throw new Error(`unexpected command: ${command}`)
    })
    const { getListeningPids, mocks } = await loadPortScan({ execFileSync })

    expect(getListeningPids(8648)).toEqual([1234])
    expect(mocks.execFileSync).not.toHaveBeenCalledWith(
      'ss',
      expect.any(Array),
      expect.any(Object),
    )
    expect(mocks.execFileSync).toHaveBeenCalledWith(
      'lsof',
      ['-tiTCP:8648', '-sTCP:LISTEN'],
      expect.objectContaining({ encoding: 'utf-8', timeout: expect.any(Number) }),
    )
  })

  it('uses ss first when available', async () => {
    Object.defineProperty(process, 'platform', { value: 'linux' })

    const execFileSync = vi.fn((command: string, args: string[]) => {
      if (command === 'sh' && args.at(-1) === 'ss') {
        return ''
      }
      if (command === 'ss') {
        return 'LISTEN 0 511 0.0.0.0:8648 0.0.0.0:* users:(("node",pid=4321,fd=20))\n'
      }
      throw new Error(`unexpected command: ${command}`)
    })
    const { getListeningPids } = await loadPortScan({ execFileSync })

    expect(getListeningPids(8648)).toEqual([4321])
  })

  it('parses Linux netstat listener output as a final fallback', async () => {
    const { parseUnixNetstatListeningPids } = await loadPortScan()

    expect(parseUnixNetstatListeningPids(
      [
        'tcp        0      0 0.0.0.0:8648            0.0.0.0:*               LISTEN      2468/node',
        'tcp        0      0 0.0.0.0:5173            0.0.0.0:*               LISTEN      1357/node',
      ].join('\n'),
      8648,
    )).toEqual([2468])
  })

  it('uses netstat.exe with timeout on win32', async () => {
    Object.defineProperty(process, 'platform', { value: 'win32' })
    process.env.TAHP_PORT_SCAN_TIMEOUT_MS = '2500'

    const execFileSync = vi.fn((command: string) => {
      if (command === 'netstat.exe') {
        return [
          '  TCP    0.0.0.0:8650           0.0.0.0:0              LISTENING       4242',
          '  TCP    127.0.0.1:5173         0.0.0.0:0              LISTENING       1111',
        ].join('\r\n')
      }
      throw new Error(`unexpected command: ${command}`)
    })
    const { getListeningPids, mocks } = await loadPortScan({ execFileSync })

    expect(getListeningPids(8650)).toEqual([4242])
    expect(mocks.execFileSync).toHaveBeenCalledWith(
      'netstat.exe',
      ['-ano', '-p', 'tcp'],
      expect.objectContaining({
        encoding: 'utf-8',
        timeout: 2500,
        killSignal: 'SIGKILL',
        windowsHide: true,
      }),
    )
  })

  it('returns empty list when netstat.exe times out on win32', async () => {
    Object.defineProperty(process, 'platform', { value: 'win32' })

    const timedOut = Object.assign(new Error('ETIMEDOUT'), { code: 'ETIMEDOUT' })
    const execFileSync = vi.fn(() => {
      throw timedOut
    })
    const { getListeningPids } = await loadPortScan({ execFileSync })

    expect(getListeningPids(8650)).toEqual([])
  })

  it('skips port scan entirely when TAHP_SKIP_PORT_SCAN=1', async () => {
    Object.defineProperty(process, 'platform', { value: 'win32' })
    process.env.TAHP_SKIP_PORT_SCAN = '1'

    const execFileSync = vi.fn()
    const { getListeningPids, mocks } = await loadPortScan({ execFileSync })

    expect(getListeningPids(8650)).toEqual([])
    expect(mocks.execFileSync).not.toHaveBeenCalled()
  })
})
