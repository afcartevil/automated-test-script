/**
 * conversations API stub — Conversation memory feature removed from TAHP.
 * Retained as a stub so ConversationMonitorPane.vue continues to compile.
 */

export type ConversationSummary = {
  id: string
  source: string
  model: string
  title: string | null
  started_at: number
  ended_at: number | null
  last_active: number
  message_count: number
  tool_call_count: number
  input_tokens: number
  output_tokens: number
  preview: string
  is_active: boolean
  thread_session_count: number
  estimated_cost_usd?: number
  actual_cost_usd?: number | null
  billing_provider?: string | null
}

export type ConversationMessage = {
  id: number | string
  session_id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: number
}

export type ConversationDetail = {
  session_id: string
  messages: ConversationMessage[]
  visible_count: number
  thread_session_count: number
}

export type ConversationListOptions = {
  humanOnly?: boolean
  source?: string
  limit?: number
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export async function fetchConversationSummaries(_options?: ConversationListOptions): Promise<ConversationSummary[]> {
  return []
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export async function fetchConversationDetail(_sessionId: string, _options?: ConversationListOptions): Promise<ConversationDetail | null> {
  return null
}
