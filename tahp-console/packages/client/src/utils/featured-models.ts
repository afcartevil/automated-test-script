import type { AvailableModelGroup } from '@/api/hermes/system'

/** 首页精选展示的厂商家族，按优先级排序 */
export const VENDOR_FAMILY_ORDER = [
  'deepseek',
  'minimax',
  'glm',
  'kimi',
  'qwen',
  'gpt',
  'gemini',
] as const

export type VendorFamily = (typeof VENDOR_FAMILY_ORDER)[number]

export const DASHBOARD_MODEL_LIMIT = 4

export interface FeaturedModelItem {
  name: string
  vendor: string
  model: string
  provider: string
  badge?: string
}

export interface SelectFeaturedModelsOptions {
  groups: AvailableModelGroup[]
  selectedModel: string
  selectedProvider: string
  displayModelName: (modelId: string, provider?: string) => string
  limit?: number
}

interface FlatModel {
  model: string
  provider: string
  label: string
  order: number
  model_meta?: AvailableModelGroup['model_meta']
}

/** 用分隔符边界匹配，避免 MiniMax 被 mini 误伤 */
const LIGHT_VARIANT_RE = /(?:^|[-_/])(?:flash|lite|mini|nano|air|highspeed|haiku|turbo|codex-spark|spark|free)(?:$|[-_./])/i
const SPECIALTY_RE = /(?:^|[-_/])(?:coder|reasoner|thinking)(?:$|[-_./])/i
const FLAGSHIP_PRO_RE = /(?:^|[-_/])pro(?:$|[-_./])/i
const FLAGSHIP_PLUS_RE = /(?:^|[-_/])plus(?:$|[-_./])/i
const FLAGSHIP_MAX_RE = /(?:^|[-_/])max(?:$|[-_./])/i

function modelTail(modelId: string): string {
  const id = modelId.toLowerCase()
  return id.includes('/') ? id.slice(id.lastIndexOf('/') + 1) : id
}

/** 从 model id 与 provider 推断厂商家族 */
export function detectVendorFamily(modelId: string, provider: string): VendorFamily | null {
  const id = modelId.toLowerCase()
  const tail = modelTail(modelId)
  const providerKey = provider.toLowerCase()

  if (/deepseek/.test(id)) return 'deepseek'
  if (/minimax/.test(id)) return 'minimax'
  if (/\bglm\b|glm[-_]/.test(tail) || /^glm/.test(tail)) return 'glm'
  if (/kimi/.test(id)) return 'kimi'
  if (/qwen/.test(id)) return 'qwen'
  if (/\bgpt\b|gpt[-_]/.test(tail) || /^gpt/.test(tail)) return 'gpt'
  if (/gemini/.test(id)) return 'gemini'

  if (providerKey === 'deepseek' || providerKey.includes('deepseek')) return 'deepseek'
  if (providerKey === 'minimax' || providerKey === 'minimax-cn') return 'minimax'
  if (providerKey === 'zai' || providerKey === 'glm-coding-plan') return 'glm'
  if (providerKey === 'kimi-coding-cn' || providerKey === 'moonshot') return 'kimi'
  if (providerKey === 'gemini') return 'gemini'
  if (
    providerKey === 'openai-codex'
    || providerKey === 'fun-codex'
    || providerKey === 'copilot'
    || providerKey === 'opencode-zen'
    || providerKey === 'opencode-go'
  ) return 'gpt'

  return null
}

function isLightVariant(tail: string): boolean {
  return LIGHT_VARIANT_RE.test(tail)
}

/** 档位：pro/plus/max > 基础 > specialty > 轻量 */
export function modelTierRank(modelId: string): number {
  const tail = modelTail(modelId)
  if (isLightVariant(tail)) return 0
  if (SPECIALTY_RE.test(tail)) return 1
  if (FLAGSHIP_PRO_RE.test(tail) || /[-_]pro$/.test(tail)) return 5
  if (FLAGSHIP_PLUS_RE.test(tail)) return 4
  if (FLAGSHIP_MAX_RE.test(tail)) return 3
  return 2
}

function parseVersionParts(value: string): number[] {
  return value
    .split('.')
    .map(part => Number.parseInt(part, 10))
    .filter(part => Number.isFinite(part))
}

/** 提取语义主版本，例如 M3、M2.5、v4、k2.6、glm-5.1 */
export function extractVersionParts(modelId: string): number[] {
  const tail = modelTail(modelId)

  // 优先字母前缀版本：m3 / m2.5 / v4 / k2.6
  for (const match of tail.matchAll(/(?:^|[-_])([mvk])(\d+(?:\.\d+)*)/g)) {
    return parseVersionParts(match[2])
  }

  // 品牌直连版本：glm-5.1、gpt-5.4、qwen3.6、gemini-3.1
  const brand = tail.match(/^(?:glm|gpt|qwen|gemini)[-_]?(\d+(?:\.\d+)*)/)
  if (brand) return parseVersionParts(brand[1])

  // 兜底：取首个不像日期/构建号（>=4 位纯数字）的版本片段
  for (const match of tail.matchAll(/(\d+(?:\.\d+)*)/g)) {
    if (/^\d{4,}$/.test(match[1])) continue
    return parseVersionParts(match[1])
  }

  return []
}

export function compareVersionParts(a: number[], b: number[]): number {
  const len = Math.max(a.length, b.length)
  for (let i = 0; i < len; i++) {
    const left = a[i] ?? 0
    const right = b[i] ?? 0
    if (left !== right) return left - right
  }
  return 0
}

function compareModelCandidates(left: FlatModel, right: FlatModel): number {
  const leftTail = modelTail(left.model)
  const rightTail = modelTail(right.model)
  const leftLight = isLightVariant(leftTail) ? 1 : 0
  const rightLight = isLightVariant(rightTail) ? 1 : 0
  if (leftLight !== rightLight) return leftLight - rightLight

  const versionDiff = compareVersionParts(
    extractVersionParts(left.model),
    extractVersionParts(right.model),
  )
  if (versionDiff !== 0) return -versionDiff

  const tierDiff = modelTierRank(right.model) - modelTierRank(left.model)
  if (tierDiff !== 0) return tierDiff

  return left.order - right.order
}

/** 在同厂商候选中挑选旗舰/最新大模型 */
export function pickBestModelForFamily(candidates: FlatModel[]): FlatModel | null {
  if (candidates.length === 0) return null
  if (candidates.length === 1) return candidates[0]

  const ranked = [...candidates].sort(compareModelCandidates)
  return ranked[0]
}

function flattenModels(groups: AvailableModelGroup[]): FlatModel[] {
  const items: FlatModel[] = []
  let order = 0
  for (const group of groups) {
    for (const model of group.models) {
      items.push({
        model,
        provider: group.provider,
        label: group.label,
        order: order++,
        model_meta: group.model_meta,
      })
    }
  }
  return items
}

function toFeaturedItem(
  flat: FlatModel,
  displayModelName: (modelId: string, provider?: string) => string,
): FeaturedModelItem {
  return {
    name: displayModelName(flat.model, flat.provider),
    vendor: flat.label,
    model: flat.model,
    provider: flat.provider,
    badge: flat.model_meta?.[flat.model]?.preview ? 'Preview' : undefined,
  }
}

function findFlatModel(
  flatModels: FlatModel[],
  model: string,
  provider: string,
): FlatModel | null {
  return flatModels.find(entry => entry.model === model && entry.provider === provider) || null
}

function buildPinnedSelection(
  flatModels: FlatModel[],
  selectedModel: string,
  selectedProvider: string,
  displayModelName: (modelId: string, provider?: string) => string,
): FeaturedModelItem | null {
  if (!selectedModel) return null

  const matched = findFlatModel(flatModels, selectedModel, selectedProvider)
  if (matched) return toFeaturedItem(matched, displayModelName)

  const providerGroup = flatModels.find(entry => entry.provider === selectedProvider)
  return {
    name: displayModelName(selectedModel, selectedProvider),
    vendor: providerGroup?.label || selectedProvider,
    model: selectedModel,
    provider: selectedProvider,
  }
}

/** 非优先厂商时的兜底分组，避免同系列占满剩余格子 */
function fallbackGroupKey(modelId: string, provider: string): string {
  const family = detectVendorFamily(modelId, provider)
  if (family) return `family:${family}`

  const tail = modelTail(modelId)
  if (/claude|opus|sonnet|haiku|anthropic/.test(tail) || /anthropic|fun-claude/.test(provider.toLowerCase())) {
    return 'other:claude'
  }
  if (/fable/.test(tail)) return 'other:fable'
  if (/doubao|seed/.test(tail)) return 'other:doubao'
  if (/grok/.test(tail) || provider.toLowerCase().includes('xai')) return 'other:grok'

  const brand = tail.match(/^([a-z]+)/)?.[1]
  return brand ? `other:${brand}` : `other:${provider}:${tail}`
}

/** 首页精选模型：7 厂商优先推荐，不足时用其余可用模型补齐 */
export function selectFeaturedModels(options: SelectFeaturedModelsOptions): FeaturedModelItem[] {
  const {
    groups,
    selectedModel,
    selectedProvider,
    displayModelName,
    limit = DASHBOARD_MODEL_LIMIT,
  } = options

  const flatModels = flattenModels(groups)
  const bestByFamily = new Map<VendorFamily, FlatModel>()

  for (const family of VENDOR_FAMILY_ORDER) {
    const familyCandidates = flatModels.filter(entry => detectVendorFamily(entry.model, entry.provider) === family)
    const best = pickBestModelForFamily(familyCandidates)
    if (best) bestByFamily.set(family, best)
  }

  const result: FeaturedModelItem[] = []
  const usedKeys = new Set<string>()
  const usedGroups = new Set<string>()

  const pinned = buildPinnedSelection(flatModels, selectedModel, selectedProvider, displayModelName)
  if (pinned) {
    result.push(pinned)
    usedKeys.add(`${pinned.provider}:${pinned.model}`)
    usedGroups.add(fallbackGroupKey(pinned.model, pinned.provider))
  }

  // 1) 优先：7 个厂商各取一个旗舰
  for (const family of VENDOR_FAMILY_ORDER) {
    if (result.length >= limit) break
    const groupKey = `family:${family}`
    if (usedGroups.has(groupKey)) continue

    const best = bestByFamily.get(family)
    if (!best) continue

    const key = `${best.provider}:${best.model}`
    if (usedKeys.has(key)) continue

    result.push(toFeaturedItem(best, displayModelName))
    usedKeys.add(key)
    usedGroups.add(groupKey)
  }

  // 2) 不足 4 个时：用其余可用模型按旗舰/版本择优补齐（不框死 7 厂商）
  if (result.length < limit) {
    const remaining = flatModels.filter(entry => !usedKeys.has(`${entry.provider}:${entry.model}`))
    const rankedRemaining = [...remaining].sort(compareModelCandidates)

    for (const candidate of rankedRemaining) {
      if (result.length >= limit) break

      const groupKey = fallbackGroupKey(candidate.model, candidate.provider)
      if (usedGroups.has(groupKey)) continue

      const key = `${candidate.provider}:${candidate.model}`
      if (usedKeys.has(key)) continue

      result.push(toFeaturedItem(candidate, displayModelName))
      usedKeys.add(key)
      usedGroups.add(groupKey)
    }
  }

  return result.slice(0, limit)
}
