import { describe, expect, it } from 'vitest'
import {
  defaultCollapsedTypes,
  groupApplyItems,
  inboxTabOf,
  initialApplySelection,
  matchInboxQuery,
  parseApplyItemType,
} from '@/utils/task-inbox-checklist'

describe('parseApplyItemType', () => {
  it('reads p1 / driver / software from checklist ids', () => {
    expect(parseApplyItemType('adapt-p1-charging-0001')).toBe('p1')
    expect(parseApplyItemType('adapt-driver-charging-0002')).toBe('driver')
    expect(parseApplyItemType('adapt-software-tp-0010')).toBe('software')
  })

  it('falls back to other when the id is not the checklist pattern', () => {
    expect(parseApplyItemType('custom-row')).toBe('other')
    expect(parseApplyItemType('')).toBe('other')
  })
})

describe('initialApplySelection', () => {
  const packages = [
    {
      package_id: 'pkg-ch',
      domain_label: '充电',
      pending_items: [
        { line_id: 'l1', item_id: 'adapt-software-charging-0001', title: '电量' },
        { line_id: 'l2', item_id: 'adapt-p1-charging-0001', title: 'IC' },
      ],
    },
    {
      package_id: 'pkg-tp',
      domain_label: 'TP触摸屏',
      pending_items: [
        { line_id: 'l3', item_id: 'adapt-p1-tp-0001', title: '识别' },
      ],
    },
  ]

  it('pre-selects the matched domain when the report tagged a domain', () => {
    expect(initialApplySelection({ packages, domain_unspecified: false })).toEqual({
      packageId: 'pkg-ch',
      checked: ['l1', 'l2'],
    })
  })

  it('does not pre-select items when the report has no domain', () => {
    expect(initialApplySelection({ packages, domain_unspecified: true })).toEqual({
      packageId: 'pkg-ch',
      checked: [],
    })
  })
})

describe('groupApplyItems', () => {
  it('groups in P1 / driver / software order', () => {
    const groups = groupApplyItems([
      { item_id: 'adapt-software-charging-0001' },
      { item_id: 'adapt-p1-charging-0001' },
      { item_id: 'adapt-driver-charging-0001' },
      { item_id: 'misc' },
    ])
    expect(groups.map(g => g.type)).toEqual(['p1', 'driver', 'software', 'other'])
    expect(groups[0].label).toBe('P1')
  })
})

describe('defaultCollapsedTypes', () => {
  it('collapses P1/driver for self-check reports', () => {
    expect(defaultCollapsedTypes('self-check')).toEqual(['p1', 'driver'])
    expect(defaultCollapsedTypes('adapt-pipeline')).toEqual([])
  })
})

describe('inbox helpers', () => {
  it('maps notice/kind to tabs', () => {
    expect(inboxTabOf({ kind: 'adapt-pipeline' })).toBe('pipe')
    expect(inboxTabOf({ kind: 'self-check' })).toBe('check')
    expect(inboxTabOf({ notice_type: 'verify-task' })).toBe('verify')
    expect(inboxTabOf({ notice_type: 'gki-patch' })).toBe('patch')
  })

  it('matches query case-insensitively', () => {
    expect(matchInboxQuery('KM9 · 充电', 'km9')).toBe(true)
    expect(matchInboxQuery('KM9 · 充电', '音频')).toBe(false)
    expect(matchInboxQuery('KM9', '  ')).toBe(true)
  })
})
