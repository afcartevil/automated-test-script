import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { existsSync, mkdtempSync, rmSync } from 'fs'
import { join } from 'path'
import { tmpdir } from 'os'
import * as XLSX from 'xlsx'
import {
  normalizeHeader,
  parseProjectDate,
  parseProjectInfoXlsx,
  type ProjectNodeEntry,
} from '../../packages/server/src/services/tahp/project-info-xlsx'
import {
  buildTestSchedule,
  getNextNodes,
  projectNodesConfigPath,
  saveTestPlanRules,
  syncProjectNodesFromXlsx,
  testPlanRulesConfigPath,
  validateTestPlanRules,
} from '../../packages/server/src/services/tahp/test-planning'

const SAMPLE_PROJECTS: ProjectNodeEntry[] = [
  {
    name: 'X6885',
    status: '升级中',
    nodes: {
      STR4: '2026/05/25',
      STR4A: '2026/07/07',
      STR5: '2026/07/27',
      STR6: null,
    },
  },
  {
    name: 'CL6',
    status: '升级中',
    nodes: {
      STR4: '2026/06/01',
      STR4A: '2026/07/15',
      STR5: '2026/08/10',
      STR6: null,
    },
  },
]

function writeSampleXlsx(filePath: string): void {
  const rows = [
    ['项目名称', '是否已完成升级', 'STR4', 'STR4A', 'STR 5', 'STR6'],
    ['X6885', '升级中', '2026-05-25', '2026-07-07', '2026/07/27', ''],
    ['X6850', '已完成', '2025/01/06', '', '', '2025/3/28'],
    ['CL6', '升级中', '2026-06-01 00:00:00', '2026-07-15 00:00:00', '2026/08/10', ''],
  ]
  const workbook = XLSX.utils.book_new()
  const sheet = XLSX.utils.aoa_to_sheet(rows)
  XLSX.utils.book_append_sheet(workbook, sheet, '项目信息')
  XLSX.writeFile(workbook, filePath)
}

describe('project-info-xlsx', () => {
  it('normalizes STR 5 header alias', () => {
    expect(normalizeHeader('STR 5')).toBe('STR5')
  })

  it('parses mixed date formats', () => {
    expect(parseProjectDate('2026-07-07 00:00:00')).toBe('2026/07/07')
    expect(parseProjectDate('2026/07/27')).toBe('2026/07/27')
    expect(parseProjectDate('')).toBeNull()
  })

  it('reads upgrading projects from xlsx', async () => {
    const tempDir = mkdtempSync(join(tmpdir(), 'tahp-xlsx-'))
    const xlsxPath = join(tempDir, 'project-info.xlsx')
    try {
      writeSampleXlsx(xlsxPath)
      const parsed = await parseProjectInfoXlsx(xlsxPath)
      expect(parsed.projects).toHaveLength(2)
      expect(parsed.projects[0]?.name).toBe('X6885')
      expect(parsed.projects[0]?.nodes.STR4A).toBe('2026/07/07')
      expect(parsed.projects[1]?.nodes.STR5).toBe('2026/08/10')
    } finally {
      rmSync(tempDir, { recursive: true, force: true })
    }
  })
})

describe('test-planning schedule', () => {
  const today = new Date(2026, 5, 24)

  it('picks next future node per project', () => {
    const items = getNextNodes(SAMPLE_PROJECTS, today)
    expect(items).toHaveLength(2)
    expect(items[0]).toMatchObject({
      project: 'X6885',
      node: 'STR4A',
      nodeDate: '2026/07/07',
      display: 'X6885 STR4A 2026/07/07',
    })
    expect(items[1]?.project).toBe('CL6')
  })

  it('builds active and upcoming schedule items', () => {
    const rules = [
      { node: 'STR4A' as const, offsetDays: -10, testName: 'GMS测试' },
      { node: 'STR4A' as const, offsetDays: -7, testName: '内核稳定性测试' },
    ]
    const items = buildTestSchedule(SAMPLE_PROJECTS, rules, today)

    const gms = items.find((item) => item.project === 'X6885' && item.testName === 'GMS测试')
    expect(gms).toMatchObject({
      node: 'STR4A',
      triggerDate: '2026/06/27',
      status: 'upcoming',
      display: 'X6885 STR4A 2026/06/27 GMS测试',
    })

    const kernel = items.find((item) => item.project === 'X6885' && item.testName === '内核稳定性测试')
    expect(kernel).toMatchObject({
      triggerDate: '2026/06/30',
      status: 'upcoming',
    })

    const activeItems = buildTestSchedule(SAMPLE_PROJECTS, rules, new Date(2026, 5, 30))
    const activeKernel = activeItems.find((item) => item.project === 'X6885' && item.testName === '内核稳定性测试')
    expect(activeKernel?.status).toBe('active')
  })

  it('validates rule offset range', () => {
    expect(() => validateTestPlanRules([
      { node: 'STR4A', offsetDays: -15, testName: 'GMS测试' },
    ])).toThrow(/偏移天数/)
  })
})

describe('test-planning config files', () => {
  let tempDir = ''

  beforeEach(() => {
    tempDir = mkdtempSync(join(tmpdir(), 'tahp-test-plan-'))
    process.env.TAHP_TEST_PLANNING_CONFIG_DIR = tempDir
  })

  afterEach(() => {
    delete process.env.TAHP_TEST_PLANNING_CONFIG_DIR
    if (tempDir && existsSync(tempDir)) {
      rmSync(tempDir, { recursive: true, force: true })
    }
  })

  it('syncs project nodes json from xlsx', async () => {
    const xlsxPath = join(tempDir, 'project-info.xlsx')
    writeSampleXlsx(xlsxPath)
    const file = await syncProjectNodesFromXlsx(xlsxPath)

    expect(file.projects).toHaveLength(2)
    expect(existsSync(projectNodesConfigPath())).toBe(true)
  })

  it('saves test plan rules', async () => {
    const saved = await saveTestPlanRules([
      { node: 'STR4A', offsetDays: -10, testName: 'GMS测试' },
    ])
    expect(saved.rules).toHaveLength(1)
    expect(existsSync(testPlanRulesConfigPath())).toBe(true)
  })
})
