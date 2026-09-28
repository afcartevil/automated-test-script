import { describe, expect, it } from 'vitest'
import { existsSync } from 'node:fs'
import { join } from 'node:path'
import * as XLSX from 'xlsx'
import {
  __testingGenerateXlsx,
  __testingSnapshotTestConfig,
  getAllCaseCatalogs,
  getCaseCatalogDetail,
  getSettings,
  initDeviceSelfCheck,
  normalizeBitflipRepeatCount,
  updateSettings,
} from '../../packages/server/src/services/tahp/device-self-check'
import { formatSelfCheckTestConfigMetaRows } from '../../packages/server/src/services/tahp/self-check-reports'
import { tahpPaths } from '../../packages/server/src/services/tahp/paths'

describe('device self-check bitflip catalog', () => {
  it('loads bitflip test catalog and case detail', () => {
    initDeviceSelfCheck()

    const group = getAllCaseCatalogs().find(g => g.testType === 'bitflip')
    expect(group?.label).toBe('bitflip压测')
    expect(group?.modules).toHaveLength(1)
    expect(group?.modules[0]?.module).toBe('bst')
    expect(group?.modules[0]?.moduleLabel).toBe('bitflip压测')
    expect(group?.modules[0]?.cases[0]?.caseName).toBe('bitflip压测(BAT)')

    const detail = getCaseCatalogDetail('bitflip')
    expect(detail).toHaveLength(1)
    expect(detail[0]).toMatchObject({
      testType: 'bitflip',
      module: 'bst',
      moduleLabel: 'bitflip压测',
      caseIndex: 1,
      caseName: 'bitflip压测(BAT)',
      automationMode: 'full',
    })
    expect(detail[0].preconditions).toContain('root')
    expect(detail[0].manualSteps).toContain('-r')
    expect(detail[0].expectedResult).toContain('PASS')
  })

  it('vendors BAT tool and case assets', () => {
    const pythonDir = join(tahpPaths.selfCheckDir, 'python')
    const toolDir = join(pythonDir, 'tools', 'bitflip_bat')
    expect(existsSync(join(toolDir, 'BitflipAnalysisTool.jar'))).toBe(true)
    expect(existsSync(join(toolDir, 'TestCase', 'TestCaseConfig.xlsx'))).toBe(true)
    expect(existsSync(join(toolDir, 'MT6878', 'ConditionConfig.xlsx'))).toBe(true)

    const caseDir = join(pythonDir, 'cases', 'bitflip', 'bst')
    expect(existsSync(join(caseDir, 'case1.py'))).toBe(true)
    expect(existsSync(join(caseDir, 'bst_runner.py'))).toBe(true)
    expect(existsSync(join(caseDir, 'case_info.json'))).toBe(true)
  })

  it('defaults bitflipRepeatCount to 5 and normalizes input', () => {
    expect(getSettings().bitflipRepeatCount).toBe(5)
    expect(normalizeBitflipRepeatCount(undefined)).toBe(5)
    expect(normalizeBitflipRepeatCount(0)).toBe(5)
    expect(normalizeBitflipRepeatCount(-1)).toBe(5)
    expect(normalizeBitflipRepeatCount(Number.NaN)).toBe(5)
    expect(normalizeBitflipRepeatCount(3)).toBe(3)
    expect(normalizeBitflipRepeatCount(100)).toBe(100)
    expect(normalizeBitflipRepeatCount(500)).toBe(100)
  })

  it('snapshots bitflipRepeatCount into testConfig and meta rows, without auto retest', () => {
    updateSettings({ autoTestEnabled: {}, autoTestPath: {}, bitflipRepeatCount: 8 })
    try {
      const cfg = __testingSnapshotTestConfig('bitflip', {})
      expect(cfg.bitflipRepeatCount).toBe(8)
      expect(cfg.autoRetestEnabled).toBeUndefined()
      expect(cfg.autoRetestCount).toBeUndefined()
      const rows = formatSelfCheckTestConfigMetaRows(cfg)
      expect(rows.some(r => r[0] === 'bitflip 每项重复次数 (-r)' && r[1] === '8')).toBe(true)
    } finally {
      updateSettings({ autoTestEnabled: {}, autoTestPath: {}, bitflipRepeatCount: 5 })
    }
  })

  it('generates readable xlsx cells (sharedStrings written after sheet build)', () => {
    const buffer = __testingGenerateXlsx([
      { name: '摘要', rows: [['设备', 'dev-1 (sn-1)'], ['测试类型', 'bitflip']], styles: ['', ''] },
      {
        name: 'bitflip结果',
        rows: [
          ['整体结果', 'PASS'],
          ['轮次统计', '共 2 轮：通过 2、失败 0'],
          ['每项重复次数 (-r)', '5'],
          ['测试日志目录', 'D:\\bat\\BAT-Data_2026-09-28_10-40-04'],
          [],
          ['Item', 'CPU-DVFS', 'mtk_mem_test', 'Result', 'Comment'],
          ['1', 'Default', 'PASS', 'PASS', ''],
          ['2', 'Stress', 'PASS', 'PASS', ''],
        ],
        styles: ['green', '', '', '', '', '', 'green', 'green'],
      },
    ])
    const wb = XLSX.read(buffer, { type: 'buffer' })
    expect(wb.SheetNames).toEqual(['摘要', 'bitflip结果'])

    const summaryRows = XLSX.utils.sheet_to_json(wb.Sheets['摘要'], { header: 1, defval: '' })
    expect(summaryRows[0]).toEqual(['设备', 'dev-1 (sn-1)'])
    expect(summaryRows[1]).toEqual(['测试类型', 'bitflip'])

    const bitflipRows = XLSX.utils.sheet_to_json(wb.Sheets['bitflip结果'], { header: 1, defval: '' }) as any[][]
    expect(bitflipRows[0].slice(0, 2)).toEqual(['整体结果', 'PASS'])
    expect(bitflipRows[1].slice(0, 2)).toEqual(['轮次统计', '共 2 轮：通过 2、失败 0'])
    const headerRow = bitflipRows.find(r => r[0] === 'Item')
    expect(headerRow?.slice(0, 5)).toEqual(['Item', 'CPU-DVFS', 'mtk_mem_test', 'Result', 'Comment'])
    const round1 = bitflipRows.find(r => String(r[0]) === '1')
    expect(round1?.[1]).toBe('Default')
    expect(round1?.[2]).toBe('PASS')
    expect(round1?.[3]).toBe('PASS')
  })
})
