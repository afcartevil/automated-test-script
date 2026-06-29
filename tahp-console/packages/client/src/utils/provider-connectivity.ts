import { fetchProviderModels } from '@/api/hermes/system'

const OAUTH_PROVIDER_KEYS = new Set([
  'openai-codex',
  'nous',
  'copilot',
  'xai-oauth',
])

/** Presets that do not expose OpenAI-compatible GET /v1/models. */
function isOpenAiModelsProbeCompatible(baseUrl: string): boolean {
  const u = baseUrl.trim().toLowerCase()
  if (!u) return false
  if (u.includes('anthropic.com') && !u.includes('openai')) return false
  if (u.includes('/anthropic')) return false
  return true
}

export function shouldProbeProviderConnectivity(
  providerType: 'preset' | 'custom',
  providerKey: string | null | undefined,
  baseUrl: string,
): boolean {
  const url = baseUrl.trim()
  if (!url) return false
  if (providerKey && OAUTH_PROVIDER_KEYS.has(providerKey)) return false
  if (!isOpenAiModelsProbeCompatible(url)) return false
  return providerType === 'custom' || !!providerKey
}

export async function probeProviderConnectivity(
  baseUrl: string,
  apiKey?: string,
): Promise<{ modelCount: number; models: string[] }> {
  const data = await fetchProviderModels({
    base_url: baseUrl.trim(),
    api_key: apiKey?.trim() || '',
  })
  if (!data.models?.length) {
    throw new Error('Provider 未返回可用模型列表，请检查 Base URL 与 API Key')
  }
  return { modelCount: data.models.length, models: data.models }
}
