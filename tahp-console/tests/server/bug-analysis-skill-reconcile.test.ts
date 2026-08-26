import { describe, expect, it } from 'vitest'
import {
  cancelSkillImproveReconcile,
  scheduleSkillImproveReconcile,
  SKILL_IMPROVE_RECONCILE_DELAYS_MS,
} from '../../packages/server/src/services/tahp/bug-analysis-skill-reconcile'

describe('scheduleSkillImproveReconcile', () => {
  it('uses 15s / 60s / 180s by default', () => {
    expect(SKILL_IMPROVE_RECONCILE_DELAYS_MS).toEqual([15_000, 60_000, 180_000])
  })

  it('runs at each delay and cancel skips remaining', () => {
    const queued: Array<{ id: number; ms: number; fn: () => void }> = []
    let nextId = 1
    const timers = {
      setTimeout: (fn: () => void, ms: number) => {
        const id = nextId++
        queued.push({ id, ms, fn })
        return id as unknown as ReturnType<typeof setTimeout>
      },
      clearTimeout: (handle: ReturnType<typeof setTimeout>) => {
        const id = handle as unknown as number
        const idx = queued.findIndex(q => q.id === id)
        if (idx >= 0) queued.splice(idx, 1)
      },
    }
    const ran: number[] = []
    scheduleSkillImproveReconcile('task-1', () => { ran.push(1) }, [15, 60, 180], timers)
    expect(queued.map(q => q.ms)).toEqual([15, 60, 180])
    queued[0].fn()
    expect(ran).toEqual([1])
    cancelSkillImproveReconcile('task-1', timers)
    expect(queued).toHaveLength(0)
  })
})
