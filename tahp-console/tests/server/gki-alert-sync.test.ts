import fs from 'fs'
import os from 'os'
import path from 'path'
import { afterEach, describe, expect, it } from 'vitest'
import {
  ingestFeishuBitableAlertNotice,
  listGkiNoticesForFeishuRecord,
  listGkiUpgradeNotices,
  parseGkiAlertRecord,
  updateGkiUpgradeNoticeStatus,
} from '../../packages/server/src/services/tahp/gki-upgrade-notices'
import {
  mapFeishuFieldsToAlertRecord,
  parseBitableUrl,
  planAlertIngest,
  detectAlertRule,
  isAlertingFields,
  extractLinkRecordIds,
  looksLikeFeishuRecordId,
  formatFeishuDateCell,
} from '../../packages/server/src/services/tahp/gki-alert-sync'

const tempDirs: string[] = []

function tempStorePath() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'gki-alert-sync-'))
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

describe('gki-alert-sync mapping', () => {
  it('parses wiki bitable url', () => {
    const parsed = parseBitableUrl(
      'https://transsioner.feishu.cn/wiki/JJglwZtIuiBXqbkARAPcSQesntc?table=tblV2q5qJffkFuPE&view=vewLOPzQfs',
    )
    expect(parsed?.wikiToken).toBe('JJglwZtIuiBXqbkARAPcSQesntc')
    expect(parsed?.tableId).toBe('tblV2q5qJffkFuPE')
    expect(parsed?.viewId).toBe('vewLOPzQfs')
  })

  it('maps 平台|项目 and alert rule fields', () => {
    const fields = {
      '平台|项目': 'MT6835:[KM9, KN8]',
      分支: 'tOS16.3.0_mtk_sys_release',
      指定项目: 'KM9',
      当前GKI版本: 'android13-5.15-2025-09_r9',
      kernel版本: 'kernel-5.15',
      SOC厂商: 'MTK',
      启动日期: '2026-09-01',
      完成日期: '2026-09-30',
      异常告警: 1,
      专项未及时安排: 1,
      代码未按时入库: 0,
    }
    expect(isAlertingFields(fields)).toBe(true)
    expect(detectAlertRule(fields)).toContain('专项未及时安排')
    const record = mapFeishuFieldsToAlertRecord(fields)
    expect(record?.platform).toBe('MT6835')
    expect(record?.projects).toContain('KM9')
    expect(record?.designatedProject).toBe('KM9')
    expect(record?.currentGkiVersion).toBe('android13-5.15-2025-09_r9')
  })

  it('resolves link-field 当前GKI版本 via provided display text, not rec id', () => {
    const fields = {
      '平台|项目': 'MT6835:[KM9]',
      分支: 'branch',
      当前GKI版本: ['recvdwiFQCoscv'],
      异常告警: 1,
    }
    expect(extractLinkRecordIds(fields['当前GKI版本'])).toEqual(['recvdwiFQCoscv'])
    expect(looksLikeFeishuRecordId('recvdwiFQCoscv')).toBe(true)

    const unresolved = mapFeishuFieldsToAlertRecord(fields)
    expect(unresolved?.currentGkiVersion).toBe('')

    const resolved = mapFeishuFieldsToAlertRecord(fields, {
      currentGkiVersionText: 'android13-5.15-2025-09_r9',
    })
    expect(resolved?.currentGkiVersion).toBe('android13-5.15-2025-09_r9')
  })

  it('formats Feishu unix date cells as Asia/Shanghai yyyy-MM-dd', () => {
    expect(formatFeishuDateCell(1788192000)).toBe('2026-09-01')
    expect(formatFeishuDateCell(1790697600)).toBe('2026-09-30')
    expect(formatFeishuDateCell(1788192000000)).toBe('2026-09-01')
    expect(formatFeishuDateCell('2026/09/01')).toBe('2026-09-01')

    const record = mapFeishuFieldsToAlertRecord({
      '平台|项目': 'MT6835:[KM9]',
      分支: 'branch',
      启动日期: 1788192000,
      完成日期: 1790697600,
      异常告警: 1,
    })
    expect(record?.startDate).toBe('2026-09-01')
    expect(record?.dueDate).toBe('2026-09-30')
  })
})

describe('gki-alert-sync dedupe / generation', () => {
  it('skips create when pending already exists for record', () => {
    const storePath = tempStorePath()
    const record = parseGkiAlertRecord({
      平台: 'MT6835',
      项目: 'KM9',
      指定项目: 'KM9',
      分支: 'a\nb',
      当前GKI版本: 'android13-5.15-2025-09_r9',
      启动日期: '2026-09-01',
      完成日期: '2026-09-30',
    })!
    const first = ingestFeishuBitableAlertNotice({
      sourceId: 'recA',
      recordId: 'recA',
      record,
      alertRule: '专项未及时安排',
    }, { storePath })
    expect(first.created).toBe(true)

    const second = ingestFeishuBitableAlertNotice({
      sourceId: 'recA',
      recordId: 'recA',
      record,
      alertRule: '专项未及时安排',
    }, { storePath })
    expect(second.created).toBe(false)
    expect(listGkiUpgradeNotices({ status: 'all' }, { storePath })).toHaveLength(1)

    const plan = planAlertIngest(
      { recordId: 'recA' },
      { lastSeenAlerting: true },
      listGkiNoticesForFeishuRecord('recA', { storePath }),
    )
    expect(plan.shouldCreate).toBe(false)
  })

  it('does not reopen applied notice without clear watermark', () => {
    const storePath = tempStorePath()
    const record = parseGkiAlertRecord({
      平台: 'MT6835',
      指定项目: 'KM9',
      分支: 'branch',
      当前GKI版本: 'android13-5.15-2025-09_r9',
    })!
    ingestFeishuBitableAlertNotice({
      sourceId: 'recB',
      recordId: 'recB',
      record,
    }, { storePath })
    updateGkiUpgradeNoticeStatus('recB', 'applied', { storePath })

    const plan = planAlertIngest(
      { recordId: 'recB' },
      { lastSeenAlerting: true },
      listGkiNoticesForFeishuRecord('recB', { storePath }),
    )
    expect(plan.shouldCreate).toBe(false)

    const again = ingestFeishuBitableAlertNotice({
      sourceId: 'recB',
      recordId: 'recB',
      record,
    }, { storePath })
    expect(again.created).toBe(false)
    expect(again.notice.status).toBe('applied')
  })

  it('allows new generation after clearedAt watermark', () => {
    const storePath = tempStorePath()
    const record = parseGkiAlertRecord({
      平台: 'MT6835',
      指定项目: 'KM9',
      分支: 'branch',
      当前GKI版本: 'android13-5.15-2025-09_r9',
    })!
    ingestFeishuBitableAlertNotice({
      sourceId: 'recC',
      recordId: 'recC',
      record,
    }, { storePath })
    updateGkiUpgradeNoticeStatus('recC', 'dismissed', { storePath, reason: '暂不处理' })

    const clearedAt = '2026-09-14T06:00:00.000Z'
    const plan = planAlertIngest(
      { recordId: 'recC' },
      { lastSeenAlerting: false, clearedAt },
      listGkiNoticesForFeishuRecord('recC', { storePath }),
    )
    expect(plan.shouldCreate).toBe(true)
    expect(plan.sourceId).toBe(`recC#${clearedAt}`)

    const created = ingestFeishuBitableAlertNotice({
      sourceId: plan.sourceId,
      recordId: 'recC',
      record,
      alertRule: 'GKI升级告警',
    }, { storePath })
    expect(created.created).toBe(true)
    expect(created.notice.status).toBe('pending')
    expect(listGkiUpgradeNotices({ status: 'all' }, { storePath })).toHaveLength(2)
  })

  it('silently refreshes currentGkiVersion when re-syncing existing notice', () => {
    const storePath = tempStorePath()
    const bad = parseGkiAlertRecord({
      平台: 'MT6835',
      指定项目: 'KM9',
      分支: 'branch',
      当前GKI版本: 'recvdwiFQCoscv',
    })!
    ingestFeishuBitableAlertNotice({
      sourceId: 'recD',
      recordId: 'recD',
      record: bad,
    }, { storePath })

    const fixed = parseGkiAlertRecord({
      平台: 'MT6835',
      指定项目: 'KM9',
      分支: 'branch',
      当前GKI版本: 'android13-5.15-2025-09_r9',
    })!
    const refreshed = ingestFeishuBitableAlertNotice({
      sourceId: 'recD',
      recordId: 'recD',
      record: fixed,
      alertRule: '专项未及时安排',
    }, { storePath })
    expect(refreshed.created).toBe(false)
    expect(refreshed.notice.currentGkiVersion).toBe('android13-5.15-2025-09_r9')
    expect(refreshed.notice.fromTag).toBe('android13-5.15-2025-09_r9')
    expect(refreshed.notice.text).toContain('android13-5.15-2025-09_r9')
  })
})
