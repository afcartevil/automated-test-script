import fs from 'fs'
import os from 'os'
import path from 'path'
import { afterEach, describe, expect, it } from 'vitest'
import {
  extractGkiNotifyToken,
  ingestGkiUpgradeNotice,
  listGkiUpgradeNotices,
  parseGkiUpgradeNotice,
  updateGkiUpgradeNoticeStatus,
  verifyGkiNotifyToken,
} from '../../packages/server/src/services/tahp/gki-upgrade-notices'

const tempDirs: string[] = []

function tempStorePath() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'gki-notices-'))
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

describe('gki-upgrade external notices', () => {
  it('ingests structured notice and lists as pending', () => {
    const storePath = tempStorePath()
    const { notice, created } = ingestGkiUpgradeNotice({
      source: 'tones',
      sourceId: 'job-1',
      from_tag: 'android14-5.10-2024-01',
      to_tag: 'android14-5.10-2024-02',
      title: 'GKI 区间就绪',
    }, { storePath })

    expect(created).toBe(true)
    expect(notice.status).toBe('pending')
    expect(notice.fromTag).toBe('android14-5.10-2024-01')
    expect(notice.toTag).toBe('android14-5.10-2024-02')

    const pending = listGkiUpgradeNotices({ status: 'pending' }, { storePath })
    expect(pending).toHaveLength(1)
    expect(pending[0].noticeId).toBe(notice.noticeId)
  })

  it('parses Chinese GKI upgrade wording into analysis tags', () => {
    const a = parseGkiUpgradeNotice(
      '本次GKI升级从android13-5.15-2025-09_r9升级到android13-5.15-2026-03_r16',
    )
    expect(a.fromTag).toBe('android13-5.15-2025-09_r9')
    expect(a.toTag).toBe('android13-5.15-2026-03_r16')
    expect(a.taskKind).toBe('analysis')

    const b = parseGkiUpgradeNotice(
      '需要创建GKI升级任务，当前tag点是android13-5.15-2025-09_r9，需要升级到android13-5.15-2026-03',
    )
    expect(b.fromTag).toBe('android13-5.15-2025-09_r9')
    expect(b.toTag).toBe('android13-5.15-2026-03')
    expect(b.taskKind).toBe('analysis')
  })

  it('defaults task kind to analysis even when text says 合入', () => {
    const parsed = parseGkiUpgradeNotice(
      '请合入 android14-5.10-aaa → android14-5.10-bbb',
    )
    expect(parsed.fromTag).toBe('android14-5.10-aaa')
    expect(parsed.toTag).toBe('android14-5.10-bbb')
    expect(parsed.taskKind).toBe('analysis')
  })

  it('only uses upgrade when task_kind is explicit', () => {
    const parsed = parseGkiUpgradeNotice(
      'android14-5.10-aaa -> android14-5.10-bbb',
      { task_kind: 'upgrade' },
    )
    expect(parsed.taskKind).toBe('upgrade')
  })

  it('is idempotent on sourceId', () => {
    const storePath = tempStorePath()
    const first = ingestGkiUpgradeNotice({
      text: 'android14-5.10-a -> android14-5.10-b',
      source: 'tones',
      sourceId: 'dup-1',
    }, { storePath })
    const second = ingestGkiUpgradeNotice({
      text: 'changed',
      source: 'tones',
      sourceId: 'dup-1',
    }, { storePath })

    expect(first.created).toBe(true)
    expect(second.created).toBe(false)
    expect(second.notice.noticeId).toBe(first.notice.noticeId)
  })

  it('marks applied / dismissed', () => {
    const storePath = tempStorePath()
    const { notice } = ingestGkiUpgradeNotice(
      'android14-5.10-a -> android14-5.10-b',
      { storePath },
    )
    const applied = updateGkiUpgradeNoticeStatus(notice.noticeId, 'applied', { storePath })
    expect(applied.status).toBe('applied')
    expect(listGkiUpgradeNotices({ status: 'pending' }, { storePath })).toHaveLength(0)
  })

  it('verifies notify token when configured', () => {
    expect(verifyGkiNotifyToken('any', {})).toBe(true)
    expect(verifyGkiNotifyToken('secret', { GKI_UPGRADE_NOTIFY_TOKEN: 'secret' })).toBe(true)
    expect(verifyGkiNotifyToken('wrong', { GKI_UPGRADE_NOTIFY_TOKEN: 'secret' })).toBe(false)
    expect(extractGkiNotifyToken({ authorization: 'Bearer abc' })).toBe('abc')
    expect(extractGkiNotifyToken({ 'x-gki-notify-token': 'xyz' })).toBe('xyz')
  })
})
