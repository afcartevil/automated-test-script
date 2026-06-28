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
  matchProjectToDevice,
  normalizePlanTestType,
  projectNodesConfigPath,
  saveTestPlanRules,
  syncProjectNodesFromXlsx,
  testPlanRulesConfigPath,
  validateTestPlanRules,
} from '../../packages/server/src/services/tahp/test-planning'
import {
  buildScheduleKey,
  loadPlanExecutions,
  markPlanExecutionCompleted,
} from '../../packages/server/src/services/tahp/test-plan-executions'

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

  it('builds active and upcoming schedule items with testType labels', () => {
    const rules = [
      { node: 'STR4A' as const, offsetDays: -10, testType: 'week' as const },
      { node: 'STR4A' as const, offsetDays: -7, testType: 'monkey' as const },
    ]
    const items = buildTestSchedule(SAMPLE_PROJECTS, rules, today)

    const weekItem = items.find((item) => item.project === 'X6885' && item.testType === 'week')
    expect(weekItem).toMatchObject({
      node: 'STR4A',
      triggerDate: '2026/06/27',
      phase: 'upcoming',
      testTypeLabel: '周版本测试',
      runtimeStatus: 'pending',
      displayLabel: '即将开始',
      display: 'X6885 STR4A 2026/06/27 周版本测试',
    })

    const monkeyItem = items.find((item) => item.project === 'X6885' && item.testType === 'monkey')
    expect(monkeyItem).toMatchObject({
      triggerDate: '2026/06/30',
      phase: 'upcoming',
      testTypeLabel: 'monkey测试',
    })

    const activeItems = buildTestSchedule(SAMPLE_PROJECTS, rules, new Date(2026, 5, 30))
    const activeMonkey = activeItems.find((item) => item.project === 'X6885' && item.testType === 'monkey')
    expect(activeMonkey?.phase).toBe('active')
    expect(activeMonkey?.displayLabel).toBe('进行中')
  })

  it('merges execution state into schedule items', () => {
    const rules = [{ node: 'STR4A' as const, offsetDays: -10, testType: 'monkey' as const }]
    const scheduleKey = buildScheduleKey('X6885', 'STR4A', '2026/06/27', 'monkey')
    const items = buildTestSchedule(SAMPLE_PROJECTS, rules, today, {
      [scheduleKey]: { runtimeStatus: 'no_device' },
    })
    const item = items.find(i => i.scheduleKey === scheduleKey)
    expect(item?.runtimeStatus).toBe('no_device')
    expect(item?.displayLabel).toBe('即将开始')
    expect(item?.tags).toEqual(['无设备'])
  })

  it('validates rule offset range and testType', () => {
    expect(() => validateTestPlanRules([
      { node: 'STR4A', offsetDays: -15, testType: 'week' },
    ])).toThrow(/偏移天数/)
    expect(() => validateTestPlanRules([
      { node: 'STR4A', offsetDays: -7, testType: 'invalid' as any },
    ])).toThrow(/无效测试大类/)
  })

  it('matches project code in device name', () => {
    expect(matchProjectToDevice('X6876', {
      deviceName: 'Infinix X6876',
      status: '空闲',
      role: '未分配',
    })).toBe(true)
    expect(matchProjectToDevice('X6876', {
      deviceName: 'Infinix X6876',
      status: '测试中',
      role: '测试机',
    })).toBe(false)
    expect(normalizePlanTestType('monkey测试')).toBe('monkey')
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

  it('saves test plan rules with testType', async () => {
    const saved = await saveTestPlanRules([
      { node: 'STR4A', offsetDays: -10, testType: 'monkey' },
    ])
    expect(saved.rules).toHaveLength(1)
    expect(saved.rules[0]?.testType).toBe('monkey')
    expect(existsSync(testPlanRulesConfigPath())).toBe(true)
  })

  it('persists plan execution records', async () => {
    const key = buildScheduleKey('X6876', 'STR4A', '2026/06/28', 'monkey')
    await markPlanExecutionCompleted(key)
    const records = await loadPlanExecutions()
    expect(records[key]?.runtimeStatus).toBe('completed')
  })
})
