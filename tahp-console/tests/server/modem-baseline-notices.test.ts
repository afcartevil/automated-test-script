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
  parseModemBaselineManifestText,
  extractVersionFromBaselineName,
  resolveApTrunkPlatforms,
  updateModemBaselineNoticePlatformTask,
  isModemNoticePlatformTasksComplete,
} from '../../packages/server/src/services/tahp/modem-baseline-notices'
import { parseModemPatchNotice } from '../../packages/server/src/services/tahp/modem-baseline'

const SAMPLE = {
  source: 'MergeTool',
  trunk: 'tOS_mtk_A16_vnd_trunk.xml',
  newBaseline: 't-alps-release-b0.mp1.rc-V12.9.xml',
  oldBaseline: 't-alps-release-b0.mp1.rc-V11.9.xml',
} as const

const DISPLAY_TEXT = [
  '任务：tOS_mtk_A16_vnd_trunk.xml 基线升级',
  '新基线：t-alps-release-b0.mp1.rc-V12.9.xml',
  '老基线：t-alps-release-b0.mp1.rc-V11.9.xml',
].join('\n')

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
  it('ingests MergeTool notice and lists as pending', () => {
    const storePath = tempStorePath()
    const { notice, created } = ingestModemBaselineNotice({
      ...SAMPLE,
      sourceId: 'job-1',
    }, { storePath })

    expect(created).toBe(true)
    expect(notice.status).toBe('pending')
    expect(notice.source).toBe('MergeTool')
    expect(notice.trunk).toBe(SAMPLE.trunk)
    expect(notice.newBaseline).toBe(SAMPLE.newBaseline)
    expect(notice.oldBaseline).toBe(SAMPLE.oldBaseline)
    expect(notice.version).toBe('V12.9')
    expect(notice.text).toBe(DISPLAY_TEXT)

    const pending = listModemBaselineNotices({ status: 'pending' }, { storePath })
    expect(pending).toHaveLength(1)
    expect(pending[0].noticeId).toBe(notice.noticeId)
  })

  it('is idempotent on sourceId', () => {
    const storePath = tempStorePath()
    const first = ingestModemBaselineNotice({
      ...SAMPLE,
      sourceId: 'dup-1',
    }, { storePath })
    const second = ingestModemBaselineNotice({
      ...SAMPLE,
      sourceId: 'dup-1',
      newBaseline: 't-alps-release-b0.mp1.rc-V99.9.xml',
    }, { storePath })

    expect(first.created).toBe(true)
    expect(second.created).toBe(false)
    expect(second.notice.noticeId).toBe(first.notice.noticeId)
    expect(second.notice.newBaseline).toBe(SAMPLE.newBaseline)
    expect(listModemBaselineNotices({ status: 'all' }, { storePath })).toHaveLength(1)
  })

  it('marks applied / dismissed', () => {
    const storePath = tempStorePath()
    const { notice } = ingestModemBaselineNotice({
      ...SAMPLE,
      sourceId: 'apply-1',
    }, { storePath })
    const applied = updateModemBaselineNoticeStatus(notice.noticeId, 'applied', { storePath })
    expect(applied.status).toBe('applied')
    expect(listModemBaselineNotices({ status: 'pending' }, { storePath })).toHaveLength(0)

    const { notice: other } = ingestModemBaselineNotice({
      ...SAMPLE,
      sourceId: 'dismiss-1',
      oldBaseline: 't-alps-release-b0.mp1.rc-V10.0.xml',
    }, { storePath })
    const dismissed = updateModemBaselineNoticeStatus(other.noticeId, 'dismissed', { storePath })
    expect(dismissed.status).toBe('dismissed')
  })

  it('rejects missing trunk/newBaseline/oldBaseline', () => {
    const storePath = tempStorePath()
    expect(() => ingestModemBaselineNotice({}, { storePath })).toThrow('notice_fields_required')
    expect(() => ingestModemBaselineNotice({
      source: 'MergeTool',
      trunk: SAMPLE.trunk,
      newBaseline: SAMPLE.newBaseline,
    }, { storePath })).toThrow('notice_fields_required')
    expect(() => ingestModemBaselineNotice('plain text' as any, { storePath })).toThrow('notice_fields_required')
  })

  it('adopts preferNoticeId and is idempotent on noticeId', () => {
    const storePath = tempStorePath()
    const first = ingestModemBaselineNotice(
      {
        ...SAMPLE,
        sourceId: 'job-central-1',
      },
      { storePath, preferNoticeId: 'nb-fixed-1', preferReceivedAt: '2026-08-12T01:00:00.000Z' },
    )
    expect(first.created).toBe(true)
    expect(first.notice.noticeId).toBe('nb-fixed-1')
    expect(first.notice.receivedAt).toBe('2026-08-12T01:00:00.000Z')

    const second = ingestModemBaselineNotice(
      {
        ...SAMPLE,
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

  it('parses display text for 采用并填入', () => {
    expect(parseModemBaselineManifestText(DISPLAY_TEXT)).toEqual({
      trunk: SAMPLE.trunk,
      newBaseline: SAMPLE.newBaseline,
      oldBaseline: SAMPLE.oldBaseline,
    })
    expect(extractVersionFromBaselineName(SAMPLE.newBaseline)).toBe('V12.9')
  })

  it('parseModemPatchNotice extracts version from 新基线 line', () => {
    const parsed = parseModemPatchNotice(DISPLAY_TEXT)
    expect(parsed.version).toBe('V12.9')
    expect(parsed.targetMode).toBe('mp')
    expect(parsed.warnings).toContain('no_platform_detected')
  })
})

const tempMapDirs: string[] = []

function writeApTrunkMap(mappings: unknown): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ap-trunk-map-'))
  tempMapDirs.push(dir)
  const configDir = path.join(dir, 'config')
  fs.mkdirSync(configDir, { recursive: true })
  fs.writeFileSync(path.join(configDir, 'ap-trunk-platforms.json'), JSON.stringify({ mappings }), 'utf-8')
  return path.join(configDir, 'ap-trunk-platforms.json')
}

afterEach(() => {
  while (tempMapDirs.length) {
    const dir = tempMapDirs.pop()
    if (!dir) continue
    fs.rmSync(dir, { recursive: true, force: true })
  }
})

describe('modem-baseline AP trunk → multi platform tasks', () => {
  it('resolveApTrunkPlatforms returns empty when map file missing', () => {
    const result = resolveApTrunkPlatforms('tOS_mtk_A16_vnd_trunk.xml', {
      mapPath: path.join(os.tmpdir(), 'non-existent-', `${Date.now()}.json`),
    })
    expect(result.platforms).toEqual([])
  })

  it('resolveApTrunkPlatforms reads mapping from config file', () => {
    const mapPath = writeApTrunkMap([
      {
        trunk: 'tOS_mtk_A16_vnd_trunk.xml',
        platforms: ['GEN98-S(MP1MP2)', 'GEN97-V'],
      },
    ])
    const result = resolveApTrunkPlatforms('tOS_mtk_A16_vnd_trunk.xml', { mapPath })
    expect(result.platforms).toEqual(['GEN98-S(MP1MP2)', 'GEN97-V'])
  })

  it('resolveApTrunkPlatforms returns empty for unmatched trunk', () => {
    const mapPath = writeApTrunkMap([
      { trunk: 'other.xml', platforms: ['GEN97-V'] },
    ])
    const result = resolveApTrunkPlatforms('tOS_mtk_A16_vnd_trunk.xml', { mapPath })
    expect(result.platforms).toEqual([])
  })

  it('ingest initializes platformTasks when trunk hits mapping', () => {
    const storePath = tempStorePath()
    const mapPath = writeApTrunkMap([
      {
        trunk: SAMPLE.trunk,
        platforms: ['GEN98-S(MP1MP2)', 'GEN97-V'],
      },
    ])
    const { notice, created } = ingestModemBaselineNotice(
      { ...SAMPLE, sourceId: 'multi-1' },
      { storePath, apTrunkMapPath: mapPath },
    )
    expect(created).toBe(true)
    expect(notice.platformTasks).toHaveLength(2)
    expect(notice.platformTasks?.[0]).toMatchObject({ platform: 'GEN98-S(MP1MP2)', status: 'pending' })
    expect(notice.platformTasks?.[1]).toMatchObject({ platform: 'GEN97-V', status: 'pending' })
  })

  it('ingest leaves no platformTasks when trunk misses mapping (compat)', () => {
    const storePath = tempStorePath()
    // 指向不存在的映射表，确保不命中真实仓库内 config
    const emptyMap = path.join(os.tmpdir(), `no-map-${Date.now()}.json`)
    const { notice } = ingestModemBaselineNotice(
      { ...SAMPLE, sourceId: 'no-map-1' },
      { storePath, apTrunkMapPath: emptyMap },
    )
    expect(notice.platformTasks).toBeUndefined()
  })

  it('updateModemBaselineNoticePlatformTask updates a single platform status', () => {
    const storePath = tempStorePath()
    const mapPath = writeApTrunkMap([
      {
        trunk: SAMPLE.trunk,
        platforms: ['GEN98-S(MP1MP2)', 'GEN97-V'],
      },
    ])
    const { notice } = ingestModemBaselineNotice(
      { ...SAMPLE, sourceId: 'multi-2' },
      { storePath, apTrunkMapPath: mapPath },
    )
    const updated = updateModemBaselineNoticePlatformTask(
      notice.noticeId,
      'GEN97-V',
      { status: 'done', runId: 'run-xyz' },
      { storePath },
    )
    const task = updated.platformTasks?.find(t => t.platform === 'GEN97-V')
    expect(task?.status).toBe('done')
    expect(task?.runId).toBe('run-xyz')
    // other platform untouched
    const other = updated.platformTasks?.find(t => t.platform === 'GEN98-S(MP1MP2)')
    expect(other?.status).toBe('pending')
  })

  it('updateModemBaselineNoticePlatformTask throws for unknown platform', () => {
    const storePath = tempStorePath()
    const mapPath = writeApTrunkMap([
      { trunk: SAMPLE.trunk, platforms: ['GEN97-V'] },
    ])
    const { notice } = ingestModemBaselineNotice(
      { ...SAMPLE, sourceId: 'multi-3' },
      { storePath, apTrunkMapPath: mapPath },
    )
    expect(() =>
      updateModemBaselineNoticePlatformTask(notice.noticeId, 'GEN99-T', { status: 'done' }, { storePath }),
    ).toThrow('platform_task_not_found')
  })

  it('isModemNoticePlatformTasksComplete reflects per-platform status', () => {
    const storePath = tempStorePath()
    const mapPath = writeApTrunkMap([
      { trunk: SAMPLE.trunk, platforms: ['GEN97-V', 'GEN98-S'] },
    ])
    const { notice } = ingestModemBaselineNotice(
      { ...SAMPLE, sourceId: 'multi-4' },
      { storePath, apTrunkMapPath: mapPath },
    )
    expect(isModemNoticePlatformTasksComplete(notice)).toBe(false)
    let next = updateModemBaselineNoticePlatformTask(notice.noticeId, 'GEN97-V', { status: 'done' }, { storePath })
    expect(isModemNoticePlatformTasksComplete(next)).toBe(false)
    next = updateModemBaselineNoticePlatformTask(notice.noticeId, 'GEN98-S', { status: 'skipped' }, { storePath })
    expect(isModemNoticePlatformTasksComplete(next)).toBe(true)
  })

  it('isModemNoticePlatformTasksComplete is true when no platformTasks', () => {
    const storePath = tempStorePath()
    const emptyMap = path.join(os.tmpdir(), `no-map-${Date.now()}.json`)
    const { notice } = ingestModemBaselineNotice(
      { ...SAMPLE, sourceId: 'single-1' },
      { storePath, apTrunkMapPath: emptyMap },
    )
    expect(isModemNoticePlatformTasksComplete(notice)).toBe(true)
  })
})
