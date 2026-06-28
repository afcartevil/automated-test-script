import type { ScheduleItem } from '@/api/tahp/test-planning'

export interface ScheduleTableRow {
  scheduleKey: string
  item: ScheduleItem
  showProject: boolean
  projectRowSpan: number
}

export interface ScheduleDateBlock {
  triggerDate: string
  rows: ScheduleTableRow[]
}

function annotateProjectRowSpans(items: ScheduleItem[]): ScheduleTableRow[] {
  const rows: ScheduleTableRow[] = []
  let i = 0

  while (i < items.length) {
    const project = items[i].project
    let j = i + 1
    while (j < items.length && items[j].project === project) {
      j += 1
    }
    const span = j - i
    for (let k = i; k < j; k += 1) {
      rows.push({
        scheduleKey: items[k].scheduleKey,
        item: items[k],
        showProject: k === i,
        projectRowSpan: span,
      })
    }
    i = j
  }

  return rows
}

export function buildScheduleTableView(items: ScheduleItem[]): ScheduleDateBlock[] {
  const blocks: ScheduleDateBlock[] = []
  let currentDate = ''
  let bucket: ScheduleItem[] = []

  const flush = () => {
    if (!bucket.length) return
    blocks.push({
      triggerDate: currentDate,
      rows: annotateProjectRowSpans(bucket),
    })
    bucket = []
  }

  for (const item of items) {
    if (item.triggerDate !== currentDate) {
      flush()
      currentDate = item.triggerDate
    }
    bucket.push(item)
  }
  flush()

  return blocks
}
