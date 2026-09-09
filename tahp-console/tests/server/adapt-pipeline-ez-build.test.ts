import { mkdtempSync, rmSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import {
  appendTrsysIfRootMissing,
  composeBuildTargetRaw,
  needsTrsysForTargetOs,
  parseTosMajor,
  resolveEzBuildTargets,
  winMappedPathToLinuxWorkCode,
  winMappedPathToLinuxWorkCodeOptional,
} from '../../packages/server/src/services/tahp/adapt-pipeline/win-path-to-linux'
import {
  linuxEaBuildDir,
  parseSambaSharePath,
  windowsEaBuildDir,
} from '../../packages/server/src/services/tahp/adapt-pipeline/ea-build-layout'
import { loadEzBuildScript, resolveEzBuildScriptPath } from '../../packages/server/src/services/tahp/adapt-pipeline/harness-bridge-exec'
import {
  buildTmuxStartCommand,
  buildTmuxPollCommand,
  parseTmuxPollOutput,
  detectBuildFailureInLog,
  detectBuildSuccessInLog,
  tmuxStartConfirmed,
} from '../../packages/server/src/services/tahp/adapt-pipeline/ez-build-tmux'
import { resolveHarnessSpawn } from '../../packages/server/src/services/tahp/adapt-pipeline/harness-bridge-exec'

describe('winMappedPathToLinuxWorkCode', () => {
  it('converts Z:\\foo to /work/code/$USER/foo', () => {
    expect(winMappedPathToLinuxWorkCode('Z:\\LJ9-push')).toBe('/work/code/$USER/LJ9-push')
    expect(winMappedPathToLinuxWorkCode('Z:/LJ9-push')).toBe('/work/code/$USER/LJ9-push')
    expect(winMappedPathToLinuxWorkCode('z:\\a\\b\\c')).toBe('/work/code/$USER/a/b/c')
    expect(winMappedPathToLinuxWorkCodeOptional('')).toBe('')
    expect(winMappedPathToLinuxWorkCodeOptional('Z:\\trsys')).toBe('/work/code/$USER/trsys')
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

  it('appends trsys when NEW_TRSYSTEM_ROOT is empty', () => {
    expect(appendTrsysIfRootMissing(['sys', 'krn'], '')).toEqual(['sys', 'krn'])
    expect(appendTrsysIfRootMissing(['sys', 'trsys'], '')).toEqual(['sys', 'trsys'])
    expect(appendTrsysIfRootMissing(['sys'], 'Z:\\trsys')).toEqual(['sys'])
  })

  it('only keeps trsys for tOS17+ target os', () => {
    expect(parseTosMajor('16.3')).toBe(16)
    expect(parseTosMajor('tOS17.0')).toBe(17)
    expect(needsTrsysForTargetOs('16')).toBe(false)
    expect(needsTrsysForTargetOs('17.0')).toBe(true)
    expect(needsTrsysForTargetOs('18')).toBe(true)
    expect(resolveEzBuildTargets({ targets: ['sys', 'trsys'], toOs: '16' })).toEqual(['sys'])
    expect(resolveEzBuildTargets({ targets: ['sys'], trsysRoot: '', toOs: '17' })).toEqual(['sys'])
    expect(resolveEzBuildTargets({ targets: ['sys', 'trsys'], trsysRoot: '', toOs: '17' })).toEqual(['sys', 'trsys'])
    expect(resolveEzBuildTargets({ targets: ['sys'], trsysRoot: '', toOs: '16.3' })).toEqual(['sys'])
  })
})

describe('ea-build samba layout', () => {
  it('parses whoami + testparm path for the current user', () => {
    const raw = [
      'guansen.wang',
      '===SMB===',
      '[printers]      path = /var/spool/samba',
      '[guansen.wang]  path = /work/code/guansen.wang',
      '[other]         path = /work/code/other',
    ].join('\n')
    expect(parseSambaSharePath(raw)).toBe('/work/code/guansen.wang')
    expect(linuxEaBuildDir('/work/code/guansen.wang')).toBe('/work/code/guansen.wang/ea-build')
    expect(windowsEaBuildDir('Z:')).toBe('Z:\\ea-build')
    expect(windowsEaBuildDir('y:\\')).toBe('Y:\\ea-build')
  })

  it('parses indented testparm blocks', () => {
    const raw = 'alice\n===SMB===\n[alice]\n\tpath = /work/code/alice/\n'
    expect(parseSambaSharePath(raw)).toBe('/work/code/alice')
  })
})

describe('ez-build asset', () => {
  it('loads script with 6-8 arg signature and trsys rules', () => {
    const path = resolveEzBuildScriptPath()
    expect(path.replace(/\\/g, '/')).toMatch(/ez-build\.sh$/)
    const script = loadEzBuildScript()
    expect(script).toContain('$# -lt 6 || $# -gt 8')
    expect(script).toContain('SYSTEM_DIR="$5"')
    expect(script).toContain('VENDOR_DIR="$6"')
    expect(script).toContain('TRSYS_ROOT_DIR="${7:-}"')
    expect(script).toContain('SYS_VERSION="${8:-}"')
    expect(script).toContain('sys|krn|vext|hal|odm|trsys|pack')
    expect(script).toContain('invoke_pipe_main')
    expect(script).toContain('/opt/ci/rdtool/pipe_main')
    expect(script).not.toContain('/opt/ci/civenv/bin/python3')
    expect(script).toContain('--trsystem-dir')
    expect(script).toContain('NEW_TRSYSTEM_ROOT empty, trsys via pipe_main')
    expect(script).toContain('TRSYS_OUT_REL_USER="target"')
    expect(script).toContain('TRSYS_OUT_REL_PIPE="code/out_trsys/target"')
    expect(script).toContain('skip EA trsys build, pack trsys_dir=')
    expect(script).not.toContain('TRSYS_ROOT_DIR is empty')
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
    expect(cmd).toContain("''")
    expect(cmd).not.toContain('build pipeline')
  })

  it('appends TRSYS_ROOT_DIR and sys_version when provided', () => {
    const cmd = buildTmuxStartCommand({
      session: 'ezb-LJ9-abc',
      project: 'LJ9',
      variant: 'userdebug',
      buildFlag: 'staging',
      targetRaw: 'sys,trsys,pack',
      systemLinux: '/work/code/$USER/LJ9-sys',
      vendorLinux: '/work/code/$USER/LJ9-vnd',
      trsysLinux: '/work/code/$USER/trsys',
      sysVersion: '16.4.0',
    })
    expect(cmd).toContain('/work/code/$USER/trsys')
    expect(cmd).toContain("'16.4.0'")
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
    expect(snap.recognized).toBe(true)
    expect(snap.doneCode).toBeNull()
    expect(snap.lines.some(l => /进行中/.test(l))).toBe(true)

    const done = parseTmuxPollOutput('---POLL---\ntmux=dead\ndone_code=1\n---LOG_TAIL---\n[ERROR] project dir not found: /x')
    expect(done.alive).toBe(false)
    expect(done.recognized).toBe(true)
    expect(done.doneCode).toBe(1)
    expect(detectBuildFailureInLog(done.lines)).toMatch(/project dir not found/)

    expect(parseTmuxPollOutput('done_code=0 \n---LOG_TAIL---\nok').doneCode).toBe(0)

    const qizhi = parseTmuxPollOutput("请选择登录账号：{ echo ---POLL---; if tmux has-session -t 'ezb-x' 2>/dev/null; then echo tmux=alive; else echo tmux=dead; fi")
    expect(qizhi.recognized).toBe(false)
    expect(qizhi.alive).toBe(false)

    expect(tmuxStartConfirmed('TMUX_STARTED:ezb-X6850Android16-871819f5f4', 'ezb-X6850Android16-871819f5f4')).toBe(true)
    expect(tmuxStartConfirmed('TMUX_STARTED:ezb-X6850Android16-60521c0193', 'ezb-X6850Android16-871819f5f4')).toBe(false)

    expect(detectBuildSuccessInLog(['pack success, log: /tmp/x'], true)).toBe(true)
    expect(detectBuildSuccessInLog(['all requested compile targets succeeded, no pack requested'], false)).toBe(true)
  })

  it('poll command avoids nested quotes that break PowerShell -File forwarding', () => {
    const cmd = buildTmuxPollCommand('ezb-lj9_h972-9141775966')
    expect(cmd).toContain('done_code=$(cat ~/code/ea-build/ezb-lj9_h972-9141775966.done)')
    expect(cmd).not.toContain('[:space:]')
    expect(cmd).not.toContain('"')
  })
})

describe('resolveHarnessSpawn', () => {
  it('keeps --command as a single argv element on Windows when harness.js exists', () => {
    const longCmd = "echo ---POLL---; if [ -f ~/x.done ]; then echo done_code=$(cat ~/x.done); else echo done_code=; fi"
    const spawned = resolveHarnessSpawn([
      '--json',
      'remote-runner',
      'bridge-exec',
      '--i-understand-this-runs-raw-shell',
      '--timeout',
      '30',
      '--command',
      longCmd,
    ])
    if (process.platform === 'win32' && spawned.command === process.execPath) {
      expect(spawned.argv[spawned.argv.length - 2]).toBe('--command')
      expect(spawned.argv[spawned.argv.length - 1]).toBe(longCmd)
      expect(spawned.argv.join('\0')).not.toContain('powershell')
    } else {
      expect(spawned.argv.includes('--command')).toBe(true)
      expect(spawned.argv.includes(longCmd)).toBe(true)
    }
  })
})

describe('buildCapability ez-build path (mocked bridge)', () => {
  let eaWinDir = ''

  beforeEach(() => {
    vi.resetModules()
    vi.useFakeTimers()
    eaWinDir = mkdtempSync(join(tmpdir(), 'ea-build-'))
    process.env.TAHP_TEST_EA_BUILD_WIN = eaWinDir
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.doUnmock('../../packages/server/src/services/tahp/adapt-pipeline/harness-bridge-exec')
    vi.doUnmock('../../packages/server/src/services/tahp/host-tool-runtime')
    vi.doUnmock('../../packages/server/src/services/tahp/harness-version-gate')
    vi.restoreAllMocks()
    delete process.env.TAHP_TEST_EA_BUILD_WIN
    rmSync(eaWinDir, { recursive: true, force: true })
  })

  it('deploys script, starts tmux, polls until done_code=0', async () => {
    const commands: string[] = []
    let polls = 0
    vi.doMock('../../packages/server/src/services/tahp/harness-version-gate', () => ({
      assertHarnessCliReady: () => undefined,
    }))
    vi.doMock('../../packages/server/src/services/tahp/host-tool-runtime', async () => {
      const actual = await vi.importActual<typeof import('../../packages/server/src/services/tahp/host-tool-runtime')>(
        '../../packages/server/src/services/tahp/host-tool-runtime',
      )
      return { ...actual, detectRemoteExecFlavor: () => 'asf-bridge' }
    })
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
          if (command.includes('testparm') || command.includes('===SMB===')) {
            return {
              status: 'ok',
              exit_code: 0,
              output: 'guansen.wang\n===SMB===\n[guansen.wang]\n\tpath = /work/code/guansen.wang\n',
            }
          }
          if (command.includes('chmod +x')) {
            return { status: 'ok', exit_code: 0, output: '18718' }
          }
          if (command.includes('tmux new-session')) {
            const started = command.match(/TMUX_STARTED:([^\s'";]+)/)?.[1]
            return { status: 'ok', exit_code: 0, output: `TMUX_STARTED:${started || 'ezb-test'}\nLOG:x\nDONE:y` }
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
    expect(commands.some(c => c.includes('testparm'))).toBe(true)
    expect(commands.some(c => c.includes('chmod +x') && c.includes('/work/code/guansen.wang/ea-build'))).toBe(true)
    expect(commands.some(c => c.includes('tmux new-session') && c.includes('bash ./ez-build.sh'))).toBe(true)
    expect(commands.some(c => c.includes('done_code=') || c.includes('---POLL---'))).toBe(true)
    expect(commands.every(c => !c.includes('build pipeline'))).toBe(true)
    const startCmd = commands.find(c => c.includes('tmux new-session'))
    expect(startCmd).toContain('/work/code/guansen.wang/ea-build')
    expect(startCmd).toContain('/work/code/$USER/LJ9-sys')
    expect(startCmd).toContain('sys,hal,pack')
  })

  it('fails when done_code!=0 even if bridge exit looks ok', async () => {
    vi.doMock('../../packages/server/src/services/tahp/harness-version-gate', () => ({
      assertHarnessCliReady: () => undefined,
    }))
    vi.doMock('../../packages/server/src/services/tahp/host-tool-runtime', async () => {
      const actual = await vi.importActual<typeof import('../../packages/server/src/services/tahp/host-tool-runtime')>(
        '../../packages/server/src/services/tahp/host-tool-runtime',
      )
      return { ...actual, detectRemoteExecFlavor: () => 'asf-bridge' }
    })
    vi.doMock('../../packages/server/src/services/tahp/adapt-pipeline/harness-bridge-exec', async () => {
      const actual = await vi.importActual<typeof import('../../packages/server/src/services/tahp/adapt-pipeline/harness-bridge-exec')>(
        '../../packages/server/src/services/tahp/adapt-pipeline/harness-bridge-exec',
      )
      return {
        ...actual,
        ensureBridgeReady: async () => ({ ready: true }),
        bridgeCancel: async () => undefined,
        bridgeExec: async (command: string) => {
          if (command.includes('testparm') || command.includes('===SMB===')) {
            return {
              status: 'ok',
              exit_code: 0,
              output: 'cl6\n===SMB===\n[cl6]\n\tpath = /work/code/cl6\n',
            }
          }
          if (command.includes('chmod +x')) return { status: 'ok', exit_code: 0, output: '1' }
          if (command.includes('base64 -d')) return { status: 'ok', exit_code: 0, output: '1' }
          if (command.includes('tmux new-session')) {
            const started = command.match(/TMUX_STARTED:([^\s'";]+)/)?.[1]
            return { status: 'ok', exit_code: 0, output: `TMUX_STARTED:${started || 'ezb-x'}` }
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

  it('falls back to ~/code/ea-build when only legacy bridge-exec exists', async () => {
    const commands: string[] = []
    vi.doMock('../../packages/server/src/services/tahp/harness-version-gate', () => ({
      assertHarnessCliReady: () => undefined,
    }))
    vi.doMock('../../packages/server/src/services/tahp/host-tool-runtime', async () => {
      const actual = await vi.importActual<typeof import('../../packages/server/src/services/tahp/host-tool-runtime')>(
        '../../packages/server/src/services/tahp/host-tool-runtime',
      )
      return { ...actual, detectRemoteExecFlavor: () => 'legacy-bridge-exec' }
    })
    vi.doMock('../../packages/server/src/services/tahp/adapt-pipeline/harness-bridge-exec', async () => {
      const actual = await vi.importActual<typeof import('../../packages/server/src/services/tahp/adapt-pipeline/harness-bridge-exec')>(
        '../../packages/server/src/services/tahp/adapt-pipeline/harness-bridge-exec',
      )
      return {
        ...actual,
        ensureBridgeReady: async () => ({ ready: true }),
        bridgeCancel: async () => undefined,
        bridgeExec: async (command: string) => {
          commands.push(command)
          if (command.includes('base64 -d')) return { status: 'ok', exit_code: 0, output: '1' }
          if (command.includes('tmux new-session')) {
            const started = command.match(/TMUX_STARTED:([^\s'";]+)/)?.[1]
            return { status: 'ok', exit_code: 0, output: `TMUX_STARTED:${started || 'ezb-x'}` }
          }
          if (command.includes('---POLL---') || command.includes('done_code=')) {
            return {
              status: 'ok',
              exit_code: 0,
              output: '---POLL---\ntmux=dead\ndone_code=0\n---LOG_TAIL---\npack success, log: /tmp/p.log',
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
      pipelineRunId: 'run-legacy',
      project: 'LJ9',
      variant: 'userdebug',
      buildFlag: 'staging',
      systemPath: 'Z:\\LJ9-sys',
      vendorPath: 'Z:\\LJ9-vnd',
      buildTargets: ['hal'],
      needPack: true,
    })

    for (let i = 0; i < 40; i++) {
      const st = await buildCapability.getStatus(runId)
      if (st.state === 'success' || st.state === 'failed') break
      await vi.advanceTimersByTimeAsync(20_000)
      await Promise.resolve()
    }
    const st = await buildCapability.getStatus(runId)
    expect(st.state).toBe('success')
    expect(commands.every(c => !c.includes('testparm'))).toBe(true)
    expect(commands.some(c => c.includes('mkdir -p ~/code/ea-build') && c.includes('base64 -d'))).toBe(true)
    const startCmd = commands.find(c => c.includes('tmux new-session'))
    expect(startCmd).toContain('~/code/ea-build')
  })
})

describe('trsys conf share helpers', () => {
  it('picks latest snapshot by mtime then name', async () => {
    const { pickLatestSnapshotName, pickConfJsonPath } = await import(
      '../../packages/server/src/services/tahp/adapt-pipeline/trsys-conf-share'
    )
    expect(pickLatestSnapshotName([
      { name: '2026.08.28.10.00.00_1', mtimeMs: 100 },
      { name: '2026.08.29.10.49.47_312690', mtimeMs: 200 },
    ])).toBe('2026.08.29.10.49.47_312690')
    expect(pickConfJsonPath('S', 'user', (p) => p.replace(/\\/g, '/').endsWith('user/.pipe/conf.json')))
      .toMatch(/user[\\/]\.pipe[\\/]conf\.json$/)
    const { resolveLatestTrsysConf } = await import(
      '../../packages/server/src/services/tahp/adapt-pipeline/trsys-conf-share'
    )
    expect(() => resolveLatestTrsysConf('../x', 'user')).toThrow(/无效/)
  })
})

describe('copyEzBuildScriptToMappedEaBuild', () => {
  it('writes ez-build.sh into dest dir', async () => {
    const fs = await import('fs')
    const { tmpdir } = await import('os')
    const { join } = await import('path')
    const { copyEzBuildScriptToMappedEaBuild } = await import(
      '../../packages/server/src/services/tahp/adapt-pipeline/ez-build-tmux'
    )
    const dir = fs.mkdtempSync(join(tmpdir(), 'ea-sh-'))
    const dest = copyEzBuildScriptToMappedEaBuild('#!/bin/bash\n', join(dir, 'ea-build'))
    expect(fs.readFileSync(dest, 'utf-8')).toBe('#!/bin/bash\n')
    fs.rmSync(dir, { recursive: true, force: true })
  })
})

describe('copyConfJsonToMappedEaBuild', () => {
  it('copies conf.json onto a dest dir and removes leftover b64', async () => {
    const fs = await import('fs')
    const { tmpdir } = await import('os')
    const { join } = await import('path')
    const { copyConfJsonToMappedEaBuild } = await import(
      '../../packages/server/src/services/tahp/adapt-pipeline/ez-build-tmux'
    )
    const dir = fs.mkdtempSync(join(tmpdir(), 'ea-conf-'))
    const src = join(dir, 'src.json')
    const destDir = join(dir, 'ea-build')
    fs.writeFileSync(src, '{"ok":1}')
    fs.mkdirSync(destDir)
    fs.writeFileSync(join(destDir, 'conf.json.b64'), 'stale')
    const dest = copyConfJsonToMappedEaBuild(src, destDir)
    expect(fs.readFileSync(dest, 'utf-8')).toBe('{"ok":1}')
    expect(fs.existsSync(join(destDir, 'conf.json.b64'))).toBe(false)
    fs.rmSync(dir, { recursive: true, force: true })
  })
})

describe('buildConfDeployCommands', () => {
  it('chunks base64 into short append commands', async () => {
    const { buildConfDeployCommands } = await import(
      '../../packages/server/src/services/tahp/adapt-pipeline/ez-build-tmux'
    )
    const cmds = buildConfDeployCommands('ABCDEFGHIJ', 4)
    expect(cmds[0]).toContain('conf.json.b64')
    expect(cmds.some(c => c.startsWith('printf %s'))).toBe(true)
    expect(cmds.at(-1)).toContain('base64 -d')
    expect(cmds.filter(c => c.startsWith('printf %s')).length).toBe(3)
  })
})
