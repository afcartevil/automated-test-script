import { describe, expect, it } from 'vitest'
import type { Message } from '@/stores/hermes/chat'
import {
  afterToolStarted,
  createRunAssistState,
  pickContentTarget,
  pickReasoningTarget,
  registerReasoningMessage,
  shouldHideSupersededReasoningOnlyMessage,
} from '@/utils/run-stream-assistant'

function msg(partial: Partial<Message> & Pick<Message, 'id' | 'role'>): Message {
  return {
    content: '',
    timestamp: 0,
    ...partial,
  }
}

describe('run-stream-assistant', () => {
  it('reuses runReasoningMessageId across tool boundaries', () => {
    const state = createRunAssistState()
    const msgs = [
      msg({ id: 'a1', role: 'assistant', reasoning: 'think1', isStreaming: false }),
      msg({ id: 't1', role: 'tool', content: '' }),
    ]
    registerReasoningMessage(state, 'a1')

    expect(pickReasoningTarget(msgs, state)?.id).toBe('a1')
    afterToolStarted(msgs, state)
    expect(state.activeAssistantMessageId).toBe('a1')
    expect(pickReasoningTarget(msgs, state)?.id).toBe('a1')
  })

  it('routes content delta to reasoning bucket before answer starts', () => {
    const state = createRunAssistState()
    const msgs = [msg({ id: 'a1', role: 'assistant', reasoning: 'think', isStreaming: false })]
    registerReasoningMessage(state, 'a1')
    afterToolStarted(msgs, state)
    expect(pickContentTarget(msgs, state)?.id).toBe('a1')
  })

  it('hides superseded reasoning-only assistant bubbles', () => {
    const msgs = [
      msg({ id: 'u1', role: 'user', content: 'q' }),
      msg({ id: 'a1', role: 'assistant', reasoning: 'old think' }),
      msg({ id: 'a2', role: 'assistant', content: 'final answer' }),
    ]
    expect(shouldHideSupersededReasoningOnlyMessage(msgs, 1)).toBe(true)
    expect(shouldHideSupersededReasoningOnlyMessage(msgs, 2)).toBe(false)
  })
})
