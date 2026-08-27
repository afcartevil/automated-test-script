import { describe, expect, it } from 'vitest'
import {
  BRIDGE_EXIT_MARKER,
  asfBridgeWaitSec,
  asfBridgeCliTimeoutMs,
  asfNeedsZellijSetup,
  asfZellijMissingFromDoctor,
  flavorFromHelpText,
  isTransientAsfBridgeFailure,
  isAsfBridgeSshDisconnected,
  hasBridgeExitToken,
  parseWrappedRemoteResult,
  parseZellijLsShort,
  pickAsfUpSession,
  classifyAsfBridgeSlots,
  wrapRemoteShellForExitCode,
} from '../../packages/server/src/services/tahp/host-tool-runtime'

describe('host-tool-runtime remote flavor', () => {
  it('keeps legacy machines on bridge-exec', () => {
    expect(flavorFromHelpText(
      'Usage: harness remote-runner bridge-exec --command <shell>',
      '',
    )).toBe('legacy-bridge-exec')
  })

  it('selects asf bridge cmd when bridge-exec is gone', () => {
    expect(flavorFromHelpText(
      'Usage: asf remote-runner exec|discover',
      'Usage: asf bridge cmd --session N "<shell>"',
    )).toBe('asf-bridge')
  })

  it('is unavailable when neither remote exec path exists', () => {
    expect(flavorFromHelpText('Usage: asf --help', 'Usage: asf doctor')).toBe('unavailable')
  })
})

describe('host-tool-runtime exit wrapping', () => {
  it('wraps remote shell with a provided exit marker', () => {
    expect(wrapRemoteShellForExitCode('ls /tmp;', BRIDGE_EXIT_MARKER)).toBe(`{ ls /tmp; }; echo ${BRIDGE_EXIT_MARKER}$?`)
  })

  it('parses wrapped stdout for a specific token and ignores stale markers', () => {
    const token = 'TAHP_BRIDGE_EXIT_abc123:'
    const parsed = parseWrappedRemoteResult(
      'hello\nTAHP_BRIDGE_EXIT:0\nstale\nTAHP_BRIDGE_EXIT_abc123:7\n',
      token,
    )
    expect(parsed.output).toBe('hello\nstale')
    expect(parsed.exit_code).toBe(7)
    expect(parseWrappedRemoteResult('no marker', token)).toEqual({ output: 'no marker', exit_code: null })
  })

  it('hasBridgeExitToken only matches the command token', () => {
    expect(hasBridgeExitToken('TAHP_BRIDGE_EXIT:0\n', 'TAHP_BRIDGE_EXIT_x:')).toBe(false)
    expect(hasBridgeExitToken('TAHP_BRIDGE_EXIT_x:3\n', 'TAHP_BRIDGE_EXIT_x:')).toBe(true)
  })
})

describe('asf bridge wait vs remote timeout', () => {
  it('caps cmd --wait so asf does not sleep the full remote timeout', () => {
    expect(asfBridgeWaitSec(120)).toBe(8)
    expect(asfBridgeWaitSec(1)).toBe(1)
    expect(asfBridgeWaitSec(45)).toBe(8)
  })

  it('detects zellij list-panes timeouts as transient', () => {
    expect(isTransientAsfBridgeFailure(
      'BRIDGE_CMD_FAILED: zellij timed out: zellij.EXE --session agent_session1 action list-panes --json --all',
    )).toBe(true)
    expect(isTransientAsfBridgeFailure('host CLI timeout after 53s')).toBe(true)
    expect(isTransientAsfBridgeFailure('permission denied')).toBe(false)
  })

  it('detects SSH disconnect that requires bridge up reconnect', () => {
    expect(isAsfBridgeSshDisconnected(
      'BRIDGE_SSH_DISCONNECTED: agent_session2 mux still exists but OpenSSH is gone (pane_command is local shell (C:\\windows\\system32\\cmd.exe)). Slot released; run asf bridge up --session 2 (or omit --session) to reconnect.',
    )).toBe(true)
    expect(isAsfBridgeSshDisconnected(
      'BRIDGE_CMD_FAILED zellij failed (...): There is no active session!',
    )).toBe(true)
    expect(isAsfBridgeSshDisconnected(
      "BRIDGE_CMD_FAILED: zellij failed (--session agent_session3 action write-chars): Session 'agent_session3' not found. The following sessions are active: agent_session1",
    )).toBe(true)
    expect(isAsfBridgeSshDisconnected("qing.li3@10.205.0.143's password:")).toBe(true)
    expect(isAsfBridgeSshDisconnected('Permission denied, please try again.')).toBe(true)
    expect(isAsfBridgeSshDisconnected('Invalid password for oid16-60521c0193')).toBe(true)
    expect(isAsfBridgeSshDisconnected('请选择登录账号：\n无效的输入。请选择账号。')).toBe(true)
    expect(isAsfBridgeSshDisconnected('Password authentication\nset TERM=xterm&& ssh -tt')).toBe(true)
    expect(isAsfBridgeSshDisconnected(
      "qing.li3@10.205.0.143's password:\nPermission denied, please try again.\n---POLL---\ntmux=alive\ndone_code=\n---LOG_TAIL---\n进行中...",
    )).toBe(false)
    expect(isAsfBridgeSshDisconnected('[ERROR] Permission denied: cannot write /system')).toBe(false)
    expect(isAsfBridgeSshDisconnected('BRIDGE_CMD_FAILED: zellij timed out')).toBe(false)
    expect(isTransientAsfBridgeFailure(
      'BRIDGE_SSH_DISCONNECTED: OpenSSH is gone',
    )).toBe(false)
  })

  it('gives asf CLI enough time for two 30s zellij action timeouts', () => {
    expect(asfBridgeCliTimeoutMs(8)).toBe(98_000)
  })
})

describe('asf bridge self-heal', () => {
  it('detects missing zellij from doctor tools', () => {
    expect(asfZellijMissingFromDoctor({
      tools: [{ name: 'zellij', ok: true, detail: 'found' }],
    })).toBe(false)
    expect(asfZellijMissingFromDoctor({
      tools: [{ name: 'zellij', ok: false }],
    })).toBe(true)
    expect(asfZellijMissingFromDoctor({ tools: [] })).toBe(true)
  })

  it('treats hung bridge up as recoverable when another slot is already ready', () => {
    expect(isTransientAsfBridgeFailure('host CLI timeout after 180s')).toBe(true)
    const slots = [
      { session: 1, phase: 'missing', message: 'zellij timed out: list-panes' },
      { session: 2, phase: 'ready', message: 'agent_session ready' },
    ]
    expect(slots.find(s => s.phase === 'ready')?.session).toBe(2)
  })

  it('skips ghost agent_session1 and picks session 2', () => {
    expect(parseZellijLsShort('agent_session1\n')).toEqual(['agent_session1'])
    expect(pickAsfUpSession({
      slots: [
        { session: 1, phase: 'missing', message: 'zellij timed out: list-panes' },
        { session: 2, phase: 'missing', message: 'status.json missing' },
      ],
      muxNames: ['agent_session1'],
    })).toBe(2)
  })

  it('does not trust ls READY when zellij has no matching mux (screenshot case)', () => {
    const classified = classifyAsfBridgeSlots({
      slots: [
        { session: 1, phase: 'idle' },
        { session: 3, phase: 'ready', message: 'agent_session ready' },
      ],
      muxNames: ['agent_session1'],
    })
    expect(classified.readyWithMux).toEqual([])
    expect(classified.staleReady).toEqual([3])
    expect(classified.muxSessions).toEqual([1])
    expect(classified.upSession).toBe(2)
    expect(pickAsfUpSession({
      slots: [
        { session: 3, phase: 'ready', message: 'agent_session ready' },
      ],
      muxNames: ['agent_session1'],
    })).toBe(2)
  })

  it('keeps READY only when the matching agent_session mux exists', () => {
    const classified = classifyAsfBridgeSlots({
      slots: [
        { session: 1, phase: 'ready' },
        { session: 2, phase: 'idle' },
      ],
      muxNames: ['agent_session1'],
    })
    expect(classified.readyWithMux).toEqual([1])
    expect(classified.staleReady).toEqual([])
    expect(classified.upSession).toBe(2)
  })

  it('detects setup hint in CLI text', () => {
    expect(asfNeedsZellijSetup('zellij not found')).toBe(true)
    expect(asfNeedsZellijSetup('permission denied')).toBe(false)
    expect(asfNeedsZellijSetup('zellij timed out: list-panes')).toBe(false)
  })
})
