import fs from 'fs'
import os from 'os'
import path from 'path'
import { afterEach, describe, expect, it } from 'vitest'
import {
  extractGkiNotifyToken,
  ingestGkiNoticeFromTaskPackage,
  ingestGkiUpgradeNotice,
  isGkiTaskNotice,
  listGkiUpgradeNotices,
  parseGkiAlertRecords,
  parseGkiUpgradeNotice,
  tryIngestGkiNoticeFromTaskPackage,
  updateGkiUpgradeNoticeStatus,
  deleteGkiUpgradeNotice,
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

  it('requires a dismiss reason and stores it', () => {
    const storePath = tempStorePath()
    const { notice } = ingestGkiUpgradeNotice(
      'android14-5.10-a -> android14-5.10-b',
      { storePath },
    )
    expect(() => updateGkiUpgradeNoticeStatus(notice.noticeId, 'dismissed', { storePath }))
      .toThrow('dismiss_reason_required')
    expect(() => updateGkiUpgradeNoticeStatus(notice.noticeId, 'dismissed', {
      storePath,
      reason: '   ',
    })).toThrow('dismiss_reason_required')

    const dismissed = updateGkiUpgradeNoticeStatus(notice.noticeId, 'dismissed', {
      storePath,
      reason: '本迭代不升级',
    })
    expect(dismissed.status).toBe('dismissed')
    expect(dismissed.dismissReason).toBe('本迭代不升级')
    expect(listGkiUpgradeNotices({ status: 'dismissed' }, { storePath })).toHaveLength(1)
  })

  it('restores dismissed notices and deletes processed notices', () => {
    const storePath = tempStorePath()
    const { notice } = ingestGkiUpgradeNotice(
      'android14-5.10-a -> android14-5.10-b',
      { storePath },
    )

    expect(() => deleteGkiUpgradeNotice(notice.noticeId, { storePath }))
      .toThrow('cannot_delete_pending')

    const dismissed = updateGkiUpgradeNoticeStatus(notice.noticeId, 'dismissed', {
      storePath,
      reason: '本迭代不升级',
    })
    expect(dismissed.status).toBe('dismissed')

    const restored = updateGkiUpgradeNoticeStatus(notice.noticeId, 'pending', { storePath })
    expect(restored.status).toBe('pending')
    expect(restored.dismissReason).toBeUndefined()
    expect(listGkiUpgradeNotices({ status: 'pending' }, { storePath })).toHaveLength(1)

    const applied = updateGkiUpgradeNoticeStatus(notice.noticeId, 'applied', { storePath })
    expect(applied.status).toBe('applied')
    expect(() => updateGkiUpgradeNoticeStatus(notice.noticeId, 'pending', { storePath }))
      .toThrow('restore_only_dismissed')

    expect(deleteGkiUpgradeNotice(notice.noticeId, { storePath })).toEqual({
      noticeId: notice.noticeId,
    })
    expect(listGkiUpgradeNotices({ status: 'all' }, { storePath })).toHaveLength(0)
  })

  it('verifies notify token when configured', () => {
    expect(verifyGkiNotifyToken('any', {})).toBe(true)
    expect(verifyGkiNotifyToken('secret', { GKI_UPGRADE_NOTIFY_TOKEN: 'secret' })).toBe(true)
    expect(verifyGkiNotifyToken('wrong', { GKI_UPGRADE_NOTIFY_TOKEN: 'secret' })).toBe(false)
    expect(extractGkiNotifyToken({ authorization: 'Bearer abc' })).toBe('abc')
    expect(extractGkiNotifyToken({ 'x-gki-notify-token': 'xyz' })).toBe('xyz')
  })
})

describe('gki notices from central task packages', () => {
  it('detects gki-patch task packages', () => {
    expect(isGkiTaskNotice({ notice_type: 'gki-patch', package_id: 'p1' })).toBe(true)
    expect(isGkiTaskNotice({ kind: 'gki', package_id: 'p1' })).toBe(true)
    expect(isGkiTaskNotice({ notice_type: 'modem-patch', package_id: 'p1' })).toBe(false)
    expect(tryIngestGkiNoticeFromTaskPackage({ notice_type: 'modem-patch', title: 'x' })).toBeNull()
  })

  it('ingests my-task package into workbench inbox with tags from title', () => {
    const storePath = tempStorePath()
    const { notice, created } = ingestGkiNoticeFromTaskPackage({
      package_id: 'gki_1',
      notice_type: 'gki-patch',
      title: '本次GKI升级从android13-5.15-2025-09_r9升级到android13-5.15-2026-03_r16',
    }, { storePath })

    expect(created).toBe(true)
    expect(notice.noticeId).toBe('gki_1')
    expect(notice.source).toBe('central-task')
    expect(notice.sourceId).toBe('gki_1')
    expect(notice.fromTag).toBe('android13-5.15-2025-09_r9')
    expect(notice.toTag).toBe('android13-5.15-2026-03_r16')
    expect(listGkiUpgradeNotices({ status: 'pending' }, { storePath })).toHaveLength(1)
  })

  it('reads tags from payload and next query, and is idempotent on package_id', () => {
    const storePath = tempStorePath()
    const first = ingestGkiNoticeFromTaskPackage({
      package_id: 'gki_2',
      notice_type: 'gki-patch',
      title: 'GKI 升级',
      payload: {
        from_tag: 'android14-5.10-a',
        to_tag: 'android14-5.10-b',
      },
      next: '/tahp/gki-patch?from_tag=ignored&to_tag=ignored',
    }, { storePath })
    const second = tryIngestGkiNoticeFromTaskPackage({
      package_id: 'gki_2',
      notice_type: 'gki-patch',
      title: 'changed',
    }, { storePath })

    expect(first.created).toBe(true)
    expect(first.notice.fromTag).toBe('android14-5.10-a')
    expect(first.notice.toTag).toBe('android14-5.10-b')
    expect(second?.created).toBe(false)
    expect(second?.notice.noticeId).toBe('gki_2')
  })
})

const ALERT_TEXT = '【GKI升级管理-异常告警通知】 检测到 2 条「异常告警=1」的记录，命中规则：专项未及时安排（启动日期已填但升级未在进行中）。明细如下（JSON）： [ { "分支": "tOS15.1.2_mtk_sys_release\\ntOS15.1.2_mtk_A13_vnd_release", "平台": "MT6835", "项目": "X6730，X6730B, KM9，KM8n, KM8, C671N", "状态": "转维", "当前GKI版本": "android13-5.15-2025-09_r9", "EOL告警时间": "2027-01-01", "Android版本": "V", "kernel版本": "kernel-5.15", "SOC厂商": "MTK", "指定项目": "KM9", "启动日期": "2026-10-07", "完成日期": "2026-11-04", "负责人": "梁欢", "开发代表": "熊豪", "测试代表": "唐玉洁" }, { "分支": "tOS16.3.0_mtk_sys_release\\ntOS16.3.0_mtk_A13_vnd_release", "平台": "MT6835", "项目": "P681N, KN8, KM9", "状态": "转维", "当前GKI版本": "android13-5.15-2025-09_r9", "EOL告警时间": "2027-01-01", "Android版本": "B", "kernel版本": "kernel-5.15", "SOC厂商": "MTK", "指定项目": "KM9", "启动日期": "2026-09-01", "完成日期": "2026-09-30", "负责人": "梁欢", "开发代表": "熊豪", "测试代表": "唐玉洁" } ]'

describe('gki alert JSON notices', () => {
  it('parses each JSON record from an alert message', () => {
    const records = parseGkiAlertRecords(ALERT_TEXT)
    expect(records).toHaveLength(2)
    expect(records[0].platform).toBe('MT6835')
    expect(records[0].currentGkiVersion).toBe('android13-5.15-2025-09_r9')
    expect(records[0].kernelVersion).toBe('kernel-5.15')
    expect(records[0].socVendor).toBe('MTK')
    expect(records[0].startDate).toBe('2026-10-07')
    expect(records[0].dueDate).toBe('2026-11-04')
    expect(records[0].projects).toContain('KM9')
    expect(records[0].designatedProject).toBe('KM9')
    expect(records[0].branches).toContain('tOS15.1.2_mtk_sys_release')
    expect(records[0].branches).toContain('tOS15.1.2_mtk_A13_vnd_release')
    expect(records[1].startDate).toBe('2026-09-01')
    expect(records[1].branches).toContain('tOS16.3.0_mtk_sys_release')
  })

  it('creates one pending notice per alert record', () => {
    const storePath = tempStorePath()
    const result = ingestGkiUpgradeNotice({
      source: 'central-task',
      sourceId: 'gki_alert_1',
      text: ALERT_TEXT,
    }, { storePath, preferNoticeId: 'gki_alert_1' })

    expect(result.created).toBe(true)
    expect(result.createdCount).toBe(2)
    expect(result.notices).toHaveLength(2)
    expect(listGkiUpgradeNotices({ status: 'pending' }, { storePath })).toHaveLength(2)

    const first = result.notices.find(item => item.startDate === '2026-10-07')
    const second = result.notices.find(item => item.startDate === '2026-09-01')
    expect(first?.kind).toBe('alert')
    expect(first?.platform).toBe('MT6835')
    expect(first?.fromTag).toBe('android13-5.15-2025-09_r9')
    expect(first?.projects).toBe('KM9')
    expect(first?.parentSourceId).toBe('gki_alert_1')
    expect(first?.alertRule).toContain('专项未及时安排')
    expect(second?.projects).toBe('KM9')
    expect(second?.sourceId).toMatch(/^gki_alert_1#/)
  })

  it('is idempotent when the same alert message is ingested again', () => {
    const storePath = tempStorePath()
    ingestGkiUpgradeNotice({ source: 'central-task', sourceId: 'gki_alert_2', text: ALERT_TEXT }, { storePath, preferNoticeId: 'gki_alert_2' })
    const second = ingestGkiUpgradeNotice({ source: 'central-task', sourceId: 'gki_alert_2', text: ALERT_TEXT }, { storePath, preferNoticeId: 'gki_alert_2' })
    expect(second.created).toBe(false)
    expect(second.createdCount).toBe(0)
    expect(second.notices).toHaveLength(2)
    expect(listGkiUpgradeNotices({ status: 'all' }, { storePath })).toHaveLength(2)
  })

  it('replaces a previously unsplit parent blob with per-record notices', () => {
    const storePath = tempStorePath()
    ingestGkiUpgradeNotice({
      source: 'central-task',
      sourceId: 'gki_alert_3',
      text: 'android14-5.10-a -> android14-5.10-b',
    }, { storePath, preferNoticeId: 'gki_alert_3' })
    expect(listGkiUpgradeNotices({ status: 'all' }, { storePath })).toHaveLength(1)

    const result = ingestGkiUpgradeNotice({
      source: 'central-task',
      sourceId: 'gki_alert_3',
      text: ALERT_TEXT,
    }, { storePath, preferNoticeId: 'gki_alert_3' })
    expect(result.createdCount).toBe(2)
    const all = listGkiUpgradeNotices({ status: 'all' }, { storePath })
    expect(all).toHaveLength(2)
    expect(all.every(item => item.kind === 'alert')).toBe(true)
  })

  it('resplits an already stored unsplit inbox blob without a new message', () => {
    const storePath = tempStorePath()
    fs.writeFileSync(storePath, JSON.stringify([
      {
        noticeId: 'old_inbox',
        status: 'pending',
        text: ALERT_TEXT,
        title: '【GKI升级管理-异常告警通知】',
        source: 'central-task',
        sourceId: 'old_inbox',
        payload: { text: ALERT_TEXT },
        receivedAt: '2026-09-10T10:00:00.000Z',
        updatedAt: '2026-09-10T10:00:00.000Z',
      },
    ], null, 2))

    const pending = listGkiUpgradeNotices({ status: 'pending' }, { storePath })
    expect(pending).toHaveLength(2)
    expect(pending.every(item => item.kind === 'alert')).toBe(true)
    expect(pending.some(item => item.startDate === '2026-10-07')).toBe(true)
    expect(pending.some(item => item.startDate === '2026-09-01')).toBe(true)
    expect(pending.some(item => item.noticeId === 'old_inbox')).toBe(false)
  })

  it('updates stored 项目 field to 指定项目 on refresh', () => {
    const storePath = tempStorePath()
    fs.writeFileSync(storePath, JSON.stringify([
      {
        noticeId: 'alert_old_project',
        status: 'pending',
        kind: 'alert',
        text: '异常告警',
        source: 'central-task',
        sourceId: 'alert_old_project',
        projects: 'P681N, KN8, KM9',
        payload: { alertRecord: { 指定项目: 'KM9', 平台: 'MT6835', 当前GKI版本: 'android13-5.15-2025-09_r9' } },
        receivedAt: '2026-09-10T10:00:00.000Z',
        updatedAt: '2026-09-10T10:00:00.000Z',
      },
    ], null, 2))

    const pending = listGkiUpgradeNotices({ status: 'pending' }, { storePath })
    expect(pending).toHaveLength(1)
    expect(pending[0].projects).toBe('KM9')
  })
})
