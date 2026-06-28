import { describe, it, expect } from 'vitest'
import { buildScheduleTableView } from '../../packages/client/src/utils/test-plan-schedule-view'
import type { ScheduleItem } from '../../packages/client/src/api/tahp/test-planning'

function makeItem(partial: Partial<ScheduleItem> & Pick<ScheduleItem, 'scheduleKey' | 'project' | 'triggerDate' | 'testTypeLabel'>): ScheduleItem {
  return {
    node: 'STR4A',
    nodeDate: '2026/07/07',
    testType: 'monkey',
    phase: 'upcoming',
    runtimeStatus: 'pending',
    displayLabel: '即将开始',
    tags: [],
    display: '',
    ...partial,
  }
}

describe('buildScheduleTableView', () => {
  it('groups by triggerDate and merges project rows', () => {
    const items: ScheduleItem[] = [
      makeItem({
        scheduleKey: 'a',
        project: 'X6885',
        triggerDate: '2026/06/30',
        testTypeLabel: '周版本测试',
      }),
      makeItem({
        scheduleKey: 'b',
        project: 'X6885',
        triggerDate: '2026/06/30',
        testTypeLabel: 'monkey测试',
      }),
      makeItem({
        scheduleKey: 'c',
        project: 'X6886',
        triggerDate: '2026/06/30',
        testTypeLabel: '周版本测试',
      }),
    ]

    const blocks = buildScheduleTableView(items)
    expect(blocks).toHaveLength(1)
    expect(blocks[0].triggerDate).toBe('2026/06/30')
    expect(blocks[0].rows).toHaveLength(3)
    expect(blocks[0].rows[0]).toMatchObject({ showProject: true, projectRowSpan: 2 })
    expect(blocks[0].rows[1]).toMatchObject({ showProject: false, projectRowSpan: 2 })
    expect(blocks[0].rows[2]).toMatchObject({ showProject: true, projectRowSpan: 1 })
  })

  it('preserves date block order', () => {
    const items: ScheduleItem[] = [
      makeItem({ scheduleKey: '1', project: 'A', triggerDate: '2026/06/28', testTypeLabel: 'monkey测试' }),
      makeItem({ scheduleKey: '2', project: 'B', triggerDate: '2026/06/30', testTypeLabel: '周版本测试' }),
    ]

    const blocks = buildScheduleTableView(items)
    expect(blocks.map(b => b.triggerDate)).toEqual(['2026/06/28', '2026/06/30'])
  })
})
