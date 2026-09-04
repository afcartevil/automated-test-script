/** 顶栏「用本报告勾选」/「我的任务」列表的纯展示逻辑，不发请求。 */

export type ApplyItemType = 'p1' | 'driver' | 'software' | 'other'

export const APPLY_TYPE_ORDER: ApplyItemType[] = ['p1', 'driver', 'software', 'other']

export const APPLY_TYPE_LABEL: Record<ApplyItemType, string> = {
  p1: 'P1',
  driver: '驱动',
  software: '软件',
  other: '其它',
}

const ITEM_ID_RE = /^adapt-(p1|driver|software)-([a-z0-9]+)-(\d{4})$/i

export function parseApplyItemType(itemId: string): ApplyItemType {
  const match = String(itemId || '').trim().match(ITEM_ID_RE)
  if (!match) return 'other'
  return match[1].toLowerCase() as ApplyItemType
}

export type ApplyPackage = {
  package_id: string
  title?: string
  domain_label?: string
  pending_items: Array<{ line_id: string; item_id: string; title: string }>
}

export function initialApplySelection(prompt: {
  domain_unspecified?: boolean
  packages: ApplyPackage[]
}): { packageId: string; checked: string[] } {
  const first = prompt.packages[0]
  if (!first) return { packageId: '', checked: [] }
  if (prompt.domain_unspecified) return { packageId: first.package_id, checked: [] }
  return {
    packageId: first.package_id,
    checked: first.pending_items.map(item => item.line_id),
  }
}

/** 自检报告默认展开软件项，P1/驱动先收起。 */
export function defaultCollapsedTypes(dimension?: string): ApplyItemType[] {
  return dimension === 'self-check' ? ['p1', 'driver'] : []
}

export function groupApplyItems<T extends { item_id: string }>(items: T[]) {
  const buckets = new Map<ApplyItemType, T[]>()
  for (const item of items) {
    const type = parseApplyItemType(item.item_id)
    const list = buckets.get(type) || []
    list.push(item)
    buckets.set(type, list)
  }
  return APPLY_TYPE_ORDER
    .filter(type => (buckets.get(type) || []).length > 0)
    .map(type => ({
      type,
      label: APPLY_TYPE_LABEL[type],
      items: buckets.get(type)!,
    }))
}

export type InboxTab = 'all' | 'pipe' | 'check' | 'verify' | 'patch'

export function inboxTabOf(pkg: { kind?: string; notice_type?: string }): InboxTab {
  if (pkg.notice_type === 'verify-task') return 'verify'
  if (pkg.notice_type) return 'patch'
  if (pkg.kind === 'adapt-pipeline') return 'pipe'
  return 'check'
}

export function matchInboxQuery(haystack: string, query: string): boolean {
  const q = query.trim().toLowerCase()
  if (!q) return true
  return haystack.toLowerCase().includes(q)
}
