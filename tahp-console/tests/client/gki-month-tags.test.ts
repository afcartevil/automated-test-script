import { describe, expect, it } from 'vitest'
import {
  isGkiTagNewer,
  parseGkiMonthTag,
  pickSecondNewestMonthTarget,
} from '@/utils/gki-month-tags'

describe('gki month tags', () => {
  it('parses monthly GKI tags', () => {
    expect(parseGkiMonthTag('android13-5.15-2025-09_r9')).toEqual({
      tag: 'android13-5.15-2025-09_r9',
      series: 'android13-5.15',
      yearMonth: '2025-09',
      year: 2025,
      month: 9,
      revision: 9,
    })
    expect(parseGkiMonthTag('android13-5.15.240_r00')).toBeNull()
  })

  it('picks the newest r-tag of the second newest month', () => {
    const pick = pickSecondNewestMonthTarget(
      [
        'android13-5.15-2026-09_r3',
        'android13-5.15-2026-09_r1',
        'android13-5.15-2026-06_r16',
        'android13-5.15-2026-06_r4',
        'android13-5.15-2026-03_r8',
        'android12-5.10-2026-09_r2',
      ],
      'android13-5.15-2025-09_r9',
    )
    expect(pick.latestTag).toBe('android13-5.15-2026-09_r3')
    expect(pick.latestMonth).toBe('2026-09')
    expect(pick.recommendedTag).toBe('android13-5.15-2026-06_r16')
    expect(pick.recommendedMonth).toBe('2026-06')
    expect(pick.sameSeries.every(tag => tag.startsWith('android13-5.15-'))).toBe(true)
    expect(isGkiTagNewer(pick.recommendedTag, pick.fromTag)).toBe(true)
  })

  it('warns when recommended month is not newer than current GKI', () => {
    const pick = pickSecondNewestMonthTarget(
      [
        'android13-5.15-2026-09_r1',
        'android13-5.15-2026-06_r2',
      ],
      'android13-5.15-2026-09_r1',
    )
    expect(pick.recommendedTag).toBe('android13-5.15-2026-06_r2')
    expect(pick.warning).toContain('不新于当前 GKI')
  })
})
