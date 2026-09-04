import type { LocationQueryRaw } from 'vue-router'

export const HERMES_CHAT_ROUTE = 'hermes.chat'
export const HERMES_CHAT_FRESH_QUERY = 'fresh'

export function hermesChatFreshQuery(): Record<string, string> {
  return { [HERMES_CHAT_FRESH_QUERY]: String(Date.now()) }
}

export function hasHermesChatFreshQuery(query: Record<string, unknown>): boolean {
  const raw = query[HERMES_CHAT_FRESH_QUERY]
  const value = Array.isArray(raw) ? raw[0] : raw
  return value != null && String(value) !== ''
}

export function withoutHermesChatFreshQuery(
  query: Record<string, unknown>,
): LocationQueryRaw {
  const next: LocationQueryRaw = {}
  for (const [key, value] of Object.entries(query)) {
    if (key === HERMES_CHAT_FRESH_QUERY || value == null) continue
    next[key] = Array.isArray(value)
      ? value.map(item => (item == null ? null : String(item)))
      : String(value)
  }
  return next
}
