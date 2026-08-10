import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import {
  composeBuildTargetRaw,
  winMappedPathToLinuxWorkCode,
} from '../../packages/server/src/services/tahp/adapt-pipeline/win-path-to-linux'
import { loadEzBuildScript, resolveEzBuildScriptPath } from '../../packages/server/src/services/tahp/adapt-pipeline/harness-bridge-exec'
import {
  buildTmuxStartCommand,
  parseTmuxPollOutput,
  detectBuildFailureInLog,
  detectBuildSuccessInLog,
} from '../../packages/server/src/services/tahp/adapt-pipeline/ez-build-tmux'

describe('winMappedPathToLinuxWorkCode', () => {
  it('converts Z:\\foo to /work/code/$USER/foo', () => {
    expect(winMappedPathToLinuxWorkCode('Z:\\LJ9-push')).toBe('/work/code/$USER/LJ9-push')
    expect(winMappedPathToLinuxWorkCode('Z:/LJ9-push')).toBe('/work/code/$USER/LJ9-push')
    expect(winMappedPathToLinuxWorkCode('z:\\a\\b\\c')).toBe('/work/code/$USER/a/b/c')
  })

  it('rejects non-drive paths', () => {
    expect(() => winMappedPathToLinuxWorkCode('/work/code/u/x')).toThrow(/盘符/)
    expect(() => winMappedPathToLinuxWorkCode('Z:\\')).toThrow(/目录名/)
    expect(() => winMappedPathToLinuxWorkCode('')).toThrow(/空/)
  })
})

describe('composeBuildTargetRaw', () => {
  it('joins targets and appends pack when needed', () => {
    expect(composeBuildTargetRaw(['sys', 'krn'], false)).toBe('sys,krn')
    expect(composeBuildTargetRaw(['sys', 'krn'], true)).toBe('sys,krn,pack')
    expect(composeBuildTargetRaw(['sys', 'pack'], true)).toBe('sys,pack')
  })

  it('requires at least one target or pack', () => {
    expect(() => composeBuildTargetRaw([], false)).toThrow(/target/)
    expect(composeBuildTargetRaw([], true)).toBe('pack')
  })
})

describe('ez-build asset', () => {
  it('loads script with 6-arg signature', () => {
    const path = resolveEzBuildScriptPath()
    expect(path.replace(/\\/g, '/')).toMatch(/ez-build\.sh$/)
    const script = loadEzBuildScript()
    expect(script).toContain('$# -ne 6')
    expect(script).toContain('SYSTEM_DIR="$5"')
    expect(script).toContain('VENDOR_DIR="$6"')
    expect(script.includes('\r')).toBe(false)
  })
})

describe('tmux poll helpers', () => {
  it('builds tmux start command with ez-build and done file', () => {
    const cmd = buildTmuxStartCommand({
      session: 'ezb-LJ9-abc',
      project: 'LJ9',
      variant: 'userdebug',
      buildFlag: 'staging',
      targetRaw: 'sys,hal,pack',
      systemLinux: '/work/code/$USER/LJ9-sys',
      vendorLinux: '/work/code/$USER/LJ9-vnd',
    })
    expect(cmd).toContain('tmux new-session')
    expect(cmd).toContain('bash ./ez-build.sh')
    expect(cmd).toContain('/work/code/$USER/LJ9-sys')
    expect(cmd).toContain('ezb-LJ9-abc.done')
    expect(cmd).not.toContain('build pipeline')
  })

  it('parses poll output and detects fail/success log lines', () => {
    const snap = parseTmuxPollOutput([
      '---POLL---',
      'tmux=alive',
      'done_code=',
      '---LOG_TAIL---',
      '[sys][PID:1] 进行中... 12:00:00',
      '[krn][PID:2] 进行中... 12:00:00',
    ].join('\n'))
    expect(snap.alive).toBe(true)
    expect(snap.doneCode).toBeNull()
    expect(snap.lines.some(l => /进行中/.test(l))).toBe(true)

    const done = parseTmuxPollOutput('---POLL---\ntmux=dead\ndone_code=1\n---LOG_TAIL---\n[ERROR] project dir not found: /x')
    expect(done.alive).toBe(false)
    expect(done.doneCode).toBe(1)
    expect(detectBuildFailureInLog(done.lines)).toMatch(/project dir not found/)

    expect(detectBuildSuccessInLog(['pack success, log: /tmp/x'], true)).toBe(true)
    expect(detectBuildSuccessInLog(['all requested compile targets succeeded, no pack requested'], false)).toBe(true)
  })
})

describe('buildCapability ez-build path (mocked bridge)', () => {
  beforeEach(() => {
    vi.resetModules()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.doUnmock('../../packages/server/src/services/tahp/adapt-pipeline/harness-bridge-exec')
    vi.doUnmock('../../packages/server/src/services/tahp/harness-version-gate')
    vi.restoreAllMocks()
  })

  it('deploys script, starts tmux, polls until done_code=0', async () => {
    const commands: string[] = []
    let polls = 0
    vi.doMock('../../packages/server/src/services/tahp/harness-version-gate', () => ({
      assertHarnessCliReady: () => undefined,
    }))
    vi.doMock('../../packages/server/src/services/tahp/adapt-pipeline/harness-bridge-exec', async () => {
      const actual = await vi.importActual<typeof import('../../packages/server/src/services/tahp/adapt-pipeline/harness-bridge-exec')>(
        '../../packages/server/src/services/tahp/adapt-pipeline/harness-bridge-exec',
      )
      return {
        ...actual,
        discoverBridgeReady: () => ({ ready: true }),
        ensureBridgeReady: async () => ({ ready: true }),
        bridgeCancel: async () => undefined,
        bridgeExec: async (command: string) => {
          commands.push(command)
          if (command.includes('base64 -d')) {
            return { status: 'ok', exit_code: 0, output: '18718' }
          }
          if (command.includes('tmux new-session')) {
            return { status: 'ok', exit_code: 0, output: 'TMUX_STARTED:ezb-test\nLOG:x\nDONE:y' }
          }
          if (command.includes('---POLL---') || command.includes('done_code=')) {
            polls += 1
            if (polls === 1) {
              return {
                status: 'ok',
                exit_code: 0,
                output: '---POLL---\ntmux=alive\ndone_code=\n---LOG_TAIL---\n[sys][PID:1] 进行中... 12:00:00',
              }
            }
            return {
              status: 'ok',
              exit_code: 0,
              output: '---POLL---\ntmux=dead\ndone_code=0\n---LOG_TAIL---\npack success, log: /tmp/p.log',
            }
          }
          if (command.includes('kill-session')) {
            return { status: 'ok', exit_code: 0, output: '' }
          }
          return { status: 'ok', exit_code: 0, output: 'ok' }
        },
      }
    })

    const { buildCapability } = await import(
      '../../packages/server/src/services/tahp/adapt-pipeline/build-capability'
    )

    const { runId } = await buildCapability.start({
      pipelineRunId: 'run-test-ez',
      project: 'LJ9',
      variant: 'userdebug',
      buildFlag: 'staging',
      systemPath: 'Z:\\LJ9-sys',
      vendorPath: 'Z:\\LJ9-vnd',
      buildTargets: ['sys', 'hal'],
      needPack: true,
    })

    // advance timers + microtasks until finished
    for (let i = 0; i < 80; i++) {
      const st = await buildCapability.getStatus(runId)
      if (st.state === 'success' || st.state === 'failed') break
      await vi.advanceTimersByTimeAsync(20_000)
      await Promise.resolve()
    }

    const st = await buildCapability.getStatus(runId)
    expect(st.state).toBe('success')
    expect(commands.some(c => c.includes('base64 -d') && c.includes('ea-build'))).toBe(true)
    expect(commands.some(c => c.includes('tmux new-session') && c.includes('bash ./ez-build.sh'))).toBe(true)
    expect(commands.some(c => c.includes('done_code=') || c.includes('---POLL---'))).toBe(true)
    expect(commands.every(c => !c.includes('build pipeline'))).toBe(true)
    const startCmd = commands.find(c => c.includes('tmux new-session'))
    expect(startCmd).toContain('/work/code/$USER/LJ9-sys')
    expect(startCmd).toContain('sys,hal,pack')
  })

  it('fails when done_code!=0 even if bridge exit looks ok', async () => {
    vi.doMock('../../packages/server/src/services/tahp/harness-version-gate', () => ({
      assertHarnessCliReady: () => undefined,
    }))
    vi.doMock('../../packages/server/src/services/tahp/adapt-pipeline/harness-bridge-exec', async () => {
      const actual = await vi.importActual<typeof import('../../packages/server/src/services/tahp/adapt-pipeline/harness-bridge-exec')>(
        '../../packages/server/src/services/tahp/adapt-pipeline/harness-bridge-exec',
      )
      return {
        ...actual,
        ensureBridgeReady: async () => ({ ready: true }),
        bridgeCancel: async () => undefined,
        bridgeExec: async (command: string) => {
          if (command.includes('base64 -d')) return { status: 'ok', exit_code: 0, output: '1' }
          if (command.includes('tmux new-session')) {
            return { status: 'ok', exit_code: 0, output: 'TMUX_STARTED:ezb-x' }
          }
          if (command.includes('---POLL---') || command.includes('done_code=')) {
            return {
              status: 'ok',
              exit_code: 0,
              output: '---POLL---\ntmux=dead\ndone_code=1\n---LOG_TAIL---\n[ERROR] project dir not found: /x/cl6',
            }
          }
          return { status: 'ok', exit_code: 0, output: '' }
        },
      }
    })

    const { buildCapability } = await import(
      '../../packages/server/src/services/tahp/adapt-pipeline/build-capability'
    )
    const { runId } = await buildCapability.start({
      pipelineRunId: 'run-fail',
      project: 'cl6',
      variant: 'userdebug',
      buildFlag: 'stable',
      systemPath: 'Z:\\a14-rdtool\\system',
      vendorPath: 'Z:\\a14-rdtool\\system',
      buildTargets: ['krn'],
      needPack: false,
    })

    for (let i = 0; i < 40; i++) {
      const st = await buildCapability.getStatus(runId)
      if (st.state === 'success' || st.state === 'failed') break
      await vi.advanceTimersByTimeAsync(20_000)
      await Promise.resolve()
    }
    const st = await buildCapability.getStatus(runId)
    expect(st.state).toBe('failed')
    expect(String(st.error || '')).toMatch(/project dir not found|exit_code=1/)
  })
})
