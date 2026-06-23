import type { Message } from '@/stores/hermes/chat'

/** 单次 Agent run 内追踪助手气泡，避免 tool 边界产生多条「思考过程」。 */
export interface RunAssistState {
  activeAssistantMessageId: string | null
  runReasoningMessageId: string | null
}

export function createRunAssistState(): RunAssistState {
  return { activeAssistantMessageId: null, runReasoningMessageId: null }
}

export function resetRunAssistState(state: RunAssistState): void {
  state.activeAssistantMessageId = null
  state.runReasoningMessageId = null
}

function byId(msgs: Message[], id: string | null): Message | null {
  if (!id) return null
  return msgs.find(m => m.id === id) ?? null
}

/** 选择应累加 reasoning.delta 的消息（整轮 run 共用一个思考气泡）。 */
export function pickReasoningTarget(msgs: Message[], state: RunAssistState): Message | null {
  const bucket = byId(msgs, state.runReasoningMessageId)
  if (bucket?.role === 'assistant') return bucket

  const active = byId(msgs, state.activeAssistantMessageId)
  if (active?.role === 'assistant' && active.isStreaming && !active.content?.trim()) return active

  return null
}

/** 选择应累加 message.delta 的消息。 */
export function pickContentTarget(msgs: Message[], state: RunAssistState): Message | null {
  const active = byId(msgs, state.activeAssistantMessageId)
  if (active?.role === 'assistant' && active.isStreaming) return active

  const bucket = byId(msgs, state.runReasoningMessageId)
  if (bucket?.role === 'assistant' && !bucket.content?.trim()) return bucket

  return null
}

/** tool.started 后：纯思考阶段保持同一气泡，已有正文则下次正文新建气泡。 */
export function afterToolStarted(msgs: Message[], state: RunAssistState): void {
  const bucket = byId(msgs, state.runReasoningMessageId)
  if (bucket && !bucket.content?.trim()) {
    state.activeAssistantMessageId = state.runReasoningMessageId
    return
  }
  const active = byId(msgs, state.activeAssistantMessageId)
  if (active?.role === 'assistant' && active.content?.trim()) {
    state.activeAssistantMessageId = null
  }
}

export function registerReasoningMessage(state: RunAssistState, messageId: string): void {
  state.activeAssistantMessageId = messageId
  if (!state.runReasoningMessageId) {
    state.runReasoningMessageId = messageId
  }
}

export function registerContentMessage(state: RunAssistState, messageId: string): void {
  state.activeAssistantMessageId = messageId
  if (!state.runReasoningMessageId) {
    state.runReasoningMessageId = messageId
  }
}

/** 隐藏已被同轮最终答复取代的「仅思考、无正文」中间气泡（历史会话兜底）。 */
export function shouldHideSupersededReasoningOnlyMessage(msgs: Message[], idx: number): boolean {
  const m = msgs[idx]
  if (m.role !== 'assistant' || m.content?.trim() || !m.reasoning?.trim()) return false
  for (let i = idx + 1; i < msgs.length; i++) {
    if (msgs[i].role === 'user') break
    if (msgs[i].role === 'assistant' && msgs[i].content?.trim()) return true
  }
  return false
}
