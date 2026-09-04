import { describe, expect, it } from 'vitest'
import {
  HERMES_CHAT_FRESH_QUERY,
  hasHermesChatFreshQuery,
  hermesChatFreshQuery,
  withoutHermesChatFreshQuery,
} from '@/utils/chat-navigation'

describe('hermes chat fresh query', () => {
  it('marks a fresh-open query', () => {
    const q = hermesChatFreshQuery()
    expect(hasHermesChatFreshQuery(q)).toBe(true)
    expect(q[HERMES_CHAT_FRESH_QUERY]).toMatch(/^\d+$/)
  })

  it('strips the fresh flag and leaves other params', () => {
    expect(withoutHermesChatFreshQuery({
      [HERMES_CHAT_FRESH_QUERY]: '1',
      focus: 'msg-1',
    })).toEqual({ focus: 'msg-1' })
  })

  it('treats missing flag as a resume open', () => {
    expect(hasHermesChatFreshQuery({})).toBe(false)
    expect(hasHermesChatFreshQuery({ [HERMES_CHAT_FRESH_QUERY]: '' })).toBe(false)
  })
})
