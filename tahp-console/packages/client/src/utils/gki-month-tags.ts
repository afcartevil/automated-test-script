/** GKI monthly tag, e.g. android13-5.15-2025-09_r9 */

export type GkiMonthTag = {
  tag: string
  series: string
  yearMonth: string
  year: number
  month: number
  revision: number
}

const MONTH_TAG_RE = /^(android\d+-\d+\.\d+)-(\d{4})-(\d{2})(?:_r(\d+))?$/i

export function parseGkiMonthTag(tag: string): GkiMonthTag | null {
  const raw = String(tag || '').trim()
  const match = raw.match(MONTH_TAG_RE)
  if (!match) return null
  return {
    tag: raw,
    series: match[1],
    yearMonth: `${match[2]}-${match[3]}`,
    year: Number(match[2]),
    month: Number(match[3]),
    revision: match[4] ? Number(match[4]) : 0,
  }
}

function monthKey(tag: GkiMonthTag) {
  return tag.year * 100 + tag.month
}

export function isGkiTagNewer(left: string, right: string): boolean {
  const a = parseGkiMonthTag(left)
  const b = parseGkiMonthTag(right)
  if (!a || !b) return left > right
  if (monthKey(a) !== monthKey(b)) return monthKey(a) > monthKey(b)
  return a.revision > b.revision
}

function newestInMonth(tags: GkiMonthTag[], yearMonth: string): string {
  const rows = tags.filter(item => item.yearMonth === yearMonth)
  rows.sort((a, b) => b.revision - a.revision || b.tag.localeCompare(a.tag))
  return rows[0]?.tag || ''
}

export type GkiSecondNewestMonthPick = {
  series: string
  fromTag: string
  sameSeries: string[]
  latestTag: string
  latestMonth: string
  recommendedTag: string
  recommendedMonth: string
  warning: string
}

export function pickSecondNewestMonthTarget(
  tags: string[],
  fromTag: string,
): GkiSecondNewestMonthPick {
  const from = parseGkiMonthTag(fromTag)
  const parsed = tags
    .map(parseGkiMonthTag)
    .filter((item): item is GkiMonthTag => Boolean(item))
  const series = from?.series || parsed[0]?.series || ''
  const same = series ? parsed.filter(item => item.series === series) : parsed
  const months = [...new Set(same.map(item => item.yearMonth))].sort((a, b) => b.localeCompare(a))
  const latestMonth = months[0] || ''
  const recommendedMonth = months[1] || months[0] || ''
  const latestTag = newestInMonth(same, latestMonth)
  const recommendedTag = newestInMonth(same, recommendedMonth)
  let warning = ''
  if (!same.length) {
    warning = '代码仓未读到同系列月度 tag，请手动填写 To Tag'
  } else if (months.length < 2) {
    warning = '同系列只有一个月度 tag，已用该月最新 tag 作为推荐'
  } else if (from && recommendedTag && !isGkiTagNewer(recommendedTag, from.tag)) {
    warning = '推荐次新月不新于当前 GKI，请改选更新的 To Tag'
  }
  return {
    series,
    fromTag: String(fromTag || '').trim(),
    sameSeries: same.map(item => item.tag),
    latestTag,
    latestMonth,
    recommendedTag,
    recommendedMonth,
    warning,
  }
}
