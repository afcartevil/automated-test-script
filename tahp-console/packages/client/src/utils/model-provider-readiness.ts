import type { AvailableModelGroup } from '@/api/hermes/system'

/**
 * Returns true when at least one model provider has usable credentials.
 * Config-only fallback groups (no api_key / base_url / builtin) are treated as not configured.
 */
export function isModelProviderConfigured(groups: AvailableModelGroup[]): boolean {
  return groups.some((g) => {
    if (!g.models?.length) return false
    if (g.api_key?.trim()) return true
    if (g.builtin) return true
    if (g.base_url?.trim()) return true
    return false
  })
}
