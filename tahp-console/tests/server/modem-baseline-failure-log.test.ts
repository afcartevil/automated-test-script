import { describe, expect, it } from 'vitest'
import {
  describeModemRunFailure,
  inferModemRunFailureFromLogText,
} from '../../packages/server/src/services/tahp/modem-baseline'
import {
  isModemConflictLogLine,
  isModemErrorLogLine,
} from '../../packages/client/src/utils/modemBaselineLog'

describe('inferModemRunFailureFromLogText', () => {
  it('detects missing Change-Id before generic post_process noise', () => {
    const text = `
remote: ERROR: commit 8aef815: missing Change-Id in message footer
error: failed to push some refs to 'ssh://gerrit.transsion.com:29418/MODEM/x'
[conflicts] final_status=failed exit_code=1
[run] phase=resume status=failed summary=post_process_failed exit_code=1
`
    expect(inferModemRunFailureFromLogText(text)).toBe('gerrit_missing_change_id')
    expect(describeModemRunFailure('gerrit_missing_change_id')).toMatch(/Change-Id/)
  })

  it('detects ghost zellij session (ls ready but no active session)', () => {
    expect(inferModemRunFailureFromLogText(
      'BRIDGE_CMD_FAILED zellij failed (...): There is no active session!',
    )).toBe('bridge_session_dead')
  })

  it('detects generic gerrit push rejection', () => {
    expect(inferModemRunFailureFromLogText('! [remote rejected] HEAD -> refs/for/master')).toBe(
      'gerrit_push_rejected',
    )
  })
})

describe('isModemErrorLogLine', () => {
  it('keeps Change-Id / remote rejected lines', () => {
    expect(isModemErrorLogLine('remote: ERROR: commit x: missing Change-Id in message footer')).toBe(true)
    expect(isModemErrorLogLine(' ! [remote rejected] HEAD -> refs/for/master')).toBe(true)
    expect(isModemErrorLogLine('[run] FAILURE: Gerrit 推送失败')).toBe(true)
  })

  it('drops post-process failed noise that hid the real cause', () => {
    expect(isModemErrorLogLine('[conflicts] final_status=failed exit_code=1')).toBe(false)
    expect(isModemErrorLogLine('[run] phase=resume status=failed summary=post_process_failed')).toBe(false)
  })

  it('still matches conflict lines via conflict helper', () => {
    expect(isModemConflictLogLine('[conflicts] detected_files=1')).toBe(true)
  })
})
