const OAUTH_PROVIDER_KEYS = new Set([
  'openai-codex',
  'nous',
  'copilot',
  'xai-oauth',
])

function isOpenAiModelsProbeCompatible(baseUrl: string): boolean {
  const u = baseUrl.trim().toLowerCase()
  if (!u) return false
  if (u.includes('anthropic.com') && !u.includes('openai')) return false
  if (u.includes('/anthropic')) return false
  return true
}

export function shouldVerifyProviderConnectivity(
  poolKey: string | null | undefined,
  baseUrl: string,
): boolean {
  const url = baseUrl.trim()
  if (!url) return false
  if (poolKey && OAUTH_PROVIDER_KEYS.has(poolKey)) return false
  return isOpenAiModelsProbeCompatible(url)
}

export async function verifyProviderConnectivity(
  baseUrl: string,
  apiKey?: string,
): Promise<void> {
  const base = baseUrl.trim().replace(/\/+$/, '')
  if (!base) {
    throw new Error('Missing base_url')
  }

  let parsed: URL
  try {
    parsed = new URL(base)
  } catch {
    throw new Error('Invalid base_url')
  }
  if (!['http:', 'https:'].includes(parsed.protocol)) {
    throw new Error('base_url must use http or https')
  }

  const modelsUrl = /\/v\d+\/?$/.test(base) ? `${base}/models` : `${base}/v1/models`
  const headers: Record<string, string> = {}
  if (apiKey?.trim()) headers.Authorization = `Bearer ${apiKey.trim()}`

  let res: Response
  try {
    res = await fetch(modelsUrl, {
      headers,
      signal: AbortSignal.timeout(8000),
    })
  } catch (err: any) {
    const name = err?.name === 'TimeoutError' ? '连接超时' : '无法连接'
    throw new Error(`${name}：${err?.message || modelsUrl}`)
  }

  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body = await res.text()
      if (body.trim()) detail += ` — ${body.trim().slice(0, 200)}`
    } catch { /* ignore */ }
    throw new Error(`Provider 探活失败（${detail}）`)
  }

  const data = await res.json() as { data?: Array<{ id?: unknown }> }
  if (!Array.isArray(data.data) || data.data.length === 0) {
    throw new Error('Provider 返回了空的模型列表，请检查 API Key 与 Base URL')
  }
}
