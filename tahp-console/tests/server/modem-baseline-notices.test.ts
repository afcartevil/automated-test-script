import fs from 'fs'
import os from 'os'
import path from 'path'
import { afterEach, describe, expect, it } from 'vitest'
import {
  ingestModemBaselineNotice,
  listModemBaselineNotices,
  updateModemBaselineNoticeStatus,
  verifyModemNotifyToken,
  extractModemNotifyToken,
} from '../../packages/server/src/services/tahp/modem-baseline-notices'

const tempDirs: string[] = []

function tempStorePath() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'modem-notices-'))
  tempDirs.push(dir)
  return path.join(dir, 'external-notices.json')
}

afterEach(() => {
  while (tempDirs.length) {
    const dir = tempDirs.pop()
    if (!dir) continue
    fs.rmSync(dir, { recursive: true, force: true })
  }
})

describe('modem-baseline external notices', () => {
  it('ingests structured notice and lists as pending', () => {
    const storePath = tempStorePath()
    const { notice, created } = ingestModemBaselineNotice({
      source: 'tones',
      sourceId: 'job-1',
      platform: 'GEN99-V',
      version: 'V11.35',
      title: '基线升级完成',
    }, { storePath })

    expect(created).toBe(true)
    expect(notice.status).toBe('pending')
    expect(notice.text).toContain('GEN99-V')
    expect(notice.text).toContain('V11.35')

    const pending = listModemBaselineNotices({ status: 'pending' }, { storePath })
    expect(pending).toHaveLength(1)
    expect(pending[0].noticeId).toBe(notice.noticeId)
  })

  it('is idempotent on sourceId', () => {
    const storePath = tempStorePath()
    const first = ingestModemBaselineNotice({
      text: '7月基线升级 GEN99-V V11.35',
      source: 'tones',
      sourceId: 'dup-1',
    }, { storePath })
    const second = ingestModemBaselineNotice({
      text: 'changed text should not create new',
      source: 'tones',
      sourceId: 'dup-1',
    }, { storePath })

    expect(first.created).toBe(true)
    expect(second.created).toBe(false)
    expect(second.notice.noticeId).toBe(first.notice.noticeId)
    expect(listModemBaselineNotices({ status: 'all' }, { storePath })).toHaveLength(1)
  })

  it('marks applied / dismissed', () => {
    const storePath = tempStorePath()
    const { notice } = ingestModemBaselineNotice('基线升级 GEN97 V12.0', { storePath })
    const applied = updateModemBaselineNoticeStatus(notice.noticeId, 'applied', { storePath })
    expect(applied.status).toBe('applied')
    expect(listModemBaselineNotices({ status: 'pending' }, { storePath })).toHaveLength(0)

    const { notice: other } = ingestModemBaselineNotice('另一条通知 GEN98 V1.0', { storePath })
    const dismissed = updateModemBaselineNoticeStatus(other.noticeId, 'dismissed', { storePath })
    expect(dismissed.status).toBe('dismissed')
  })

  it('rejects empty notice text', () => {
    const storePath = tempStorePath()
    expect(() => ingestModemBaselineNotice({}, { storePath })).toThrow('notice_text_required')
  })

  it('adopts preferNoticeId and is idempotent on noticeId', () => {
    const storePath = tempStorePath()
    const first = ingestModemBaselineNotice(
      {
        text: '中心推送 GEN99-V V11.35',
        source: 'tones',
        sourceId: 'job-central-1',
      },
      { storePath, preferNoticeId: 'nb-fixed-1', preferReceivedAt: '2026-08-12T01:00:00.000Z' },
    )
    expect(first.created).toBe(true)
    expect(first.notice.noticeId).toBe('nb-fixed-1')
    expect(first.notice.receivedAt).toBe('2026-08-12T01:00:00.000Z')

    const second = ingestModemBaselineNotice(
      {
        text: '重复推送应幂等',
        source: 'tones',
        sourceId: 'other-source-id',
      },
      { storePath, preferNoticeId: 'nb-fixed-1' },
    )
    expect(second.created).toBe(false)
    expect(second.notice.noticeId).toBe('nb-fixed-1')
    expect(listModemBaselineNotices({ status: 'all' }, { storePath })).toHaveLength(1)
  })

  it('verifies notify token when configured', () => {
    expect(verifyModemNotifyToken('any', {})).toBe(true)
    expect(verifyModemNotifyToken('secret', { MODEM_BASELINE_NOTIFY_TOKEN: 'secret' })).toBe(true)
    expect(verifyModemNotifyToken('wrong', { MODEM_BASELINE_NOTIFY_TOKEN: 'secret' })).toBe(false)
    expect(extractModemNotifyToken({ authorization: 'Bearer abc' })).toBe('abc')
    expect(extractModemNotifyToken({ 'x-modem-notify-token': 'xyz' })).toBe('xyz')
  })
})
